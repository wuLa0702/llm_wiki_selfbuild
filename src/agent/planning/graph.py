"""
规划模块 — LangGraph 图构建 + 节点函数 + 路由逻辑

职责：
  - 定义 AgentState 状态类型
  - 初始化 LLM（支持 DeepSeek / OpenAI 兼容 API）
  - 绑定工具到 LLM
  - 构建 LangGraph StateGraph（节点、边、条件路由）
  - 提供 build_agent() 接口供编排层调用

节点流程（ReAct + Self-Correction 架构）：
  三层自修正防御：
    ① 执行前校验（validate_tool）— 步数熔断 + 动作去重 + 置信度评估
    ② 执行后验证（verify_result）— 工具输出质量检查 + 动作记录
    ③ 推理反思  （reflect_node）— LLM 评估上一步推理方向并修正策略

  前置意图分类（intent_classifier）：
    - 在每轮用户输入进入 agent 节点前，先识别意图类别
    - 问候/闲聊跳过工具绑定（节省 token，避免不必要的工具调用）
    - 知识查询确保绑定工具
    - 分类结果注入 LLM 上下文

  完整链路：
    intent_classifier → agent → extract_wm → wm_eviction
        → (有 tool_calls → validate_tool)
            → 步数超限 → summarizer（强制输出）
            → 重复/低置信 → agent（重新思考）
            → 校验通过 → approve
                → 批准 → tools → verify_result
                    → 结果有效 → agent（继续）
                    → 结果差 → reflect_node → agent（修正后重试）
                → 拒绝 → agent（基于已有知识回答）
        → (无 tool_calls → summarizer → __end__)
"""

import json
import logging
import os
import re
import time
from typing import Annotated, Any, Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from src.agent import constants as C
from src.agent.action.registry import registry
from src.agent.action.tools import read_page, search_wiki
from src.agent.memory.attention import extract_sink_content, format_sink_knowledge, update_attention_sinks
from src.agent.memory.summarizer import condense_history
from src.agent.perception.intent import classify_intent, intent_classifier_node
from src.agent.planning.prompt import REFLECTION_SYSTEM_PROMPT, SYSTEM_PROMPT
from src.agent.planning.prompt import IntentClassificationResult, ReflectionResult

load_dotenv()
logger = logging.getLogger("agent.graph")


# ── 工具列表 ──────────────────────────────────────────────────────────────────

# 向后兼容：测试代码直接引用 P1_TOOLS
# 工具实际通过 registry.py 的 init_default_tools() 在模块加载时自动注册
P1_TOOLS = registry.list_enabled()


# ── 图状态定义 ────────────────────────────────────────────────────────────────


class AgentState(TypedDict):
    """LangGraph 图共享状态

    messages: 对话 + 工具调用全链路记录
      使用 add_messages reducer 支持增量追加（非覆盖），
      这是多轮会话隔离的基础——Checkpointer 按 thread_id 持久化后，
      每轮只传新消息即可自动合并历史。

    attention_sinks: 关键信息锚定列表
      存储用户明确要求记住或频繁提及的信息，
      跨摘要压缩存活，每轮注入 LLM 上下文。
      格式: [{id, type, content, confidence, source_turn, ...}]

    working_memory: 结构化工作记忆
      系统从对话中自动提取的上下文信息（当前目标、关键事实、实体等）。
      与 attention_sinks 互补——sink 由用户驱动，WM 由系统驱动。
      使用 working_memory_reducer 增量合并而非覆盖。
      字段: {user_identity, current_goal, key_facts, tool_cache, entities_mentioned}

    step_count: 推理步数计数器（Self-Correction）
      每次 call_model 自动 +1，步数熔断器在 validate_tool 中检查。
      初始为 0，跨轮次累计。

    executed_actions: 已执行动作的哈希表（防重复）
      key = f"{tool_name}:{canonical_args}"
      value = {tool, args, result_truncated, quality}
      在 verify_result 中记录，validate_tool 中检查。

    self_correction: 自修正机制的临时标记字段
      各节点通过此字段传递阻断/校验/反思结果，
      条件路由函数读取后决定下一节点。
      字段: {validated, step_limit_reached, correction_reason,
             poor_result, poor_tools, verified, reflection_verdict}
    """
    messages: Annotated[list[BaseMessage], add_messages]
    attention_sinks: list[dict]
    working_memory: Annotated[dict[str, Any], working_memory_reducer]
    step_count: int
    executed_actions: dict[str, Any]
    self_correction: dict[str, Any]
    current_intent: dict[str, Any]


# ── 工作记忆 Reducer ─────────────────────────────────────────────────────────


def working_memory_reducer(old: dict | None, new: dict | None) -> dict:
    """工作记忆增量合并 reducer

    不同 slot 有不同合并策略：
      - key_facts / entities_mentioned: dedup 追加 + 上限截断
      - tool_cache: 最新覆盖 + 上限截断
      - user_identity: key-level merge
      - 其他: 直接覆盖
    """
    if new is None:
        return dict(old) if old else {}
    if old is None:
        return dict(new)

    merged = dict(old)

    for k, v in new.items():
        if not v and v not in (False, 0):
            continue  # skip None/empty values

        if k == C.WM_SLOT_KEY_FACTS:
            existing = merged.get(k, [])
            merged[k] = list(dict.fromkeys(existing + v))[:C.WM_MAX_FACTS]

        elif k == C.WM_SLOT_ENTITIES:
            existing = merged.get(k, [])
            merged[k] = list(dict.fromkeys(existing + v))[:C.WM_MAX_ENTITIES]

        elif k == C.WM_SLOT_TOOL_CACHE:
            existing = merged.get(k, {})
            merged_v = {**existing, **(v or {})}
            merged[k] = dict(list(merged_v.items())[:C.WM_MAX_TOOL_CACHE_ENTRIES])

        elif k == C.WM_SLOT_USER_IDENTITY:
            merged[k] = {**merged.get(k, {}), **(v or {})}

        else:
            merged[k] = v

    return merged


# ── 动作去重键生成 ────────────────────────────────────────────────────────────


def _make_action_key(tool_name: str, args: dict) -> str:
    """生成动作的唯一标识键，用于重复检测

    规范化策略：
      - search_wiki: query 转为小写去除首尾空格
      - read_page:   path 规范化
      - query_graph: question 转为小写
      - 其他: json.dumps sort_keys

    Args:
        tool_name: 工具名（如 "search_wiki"）
        args: 工具参数字典

    Returns:
        规范化后的键字符串
    """
    if tool_name == "search_wiki":
        query = str(args.get("query", "")).lower().strip()
        return f"search_wiki|{query}"
    if tool_name == "read_page":
        path = str(args.get("path", "")).strip()
        offset = args.get("offset", 0)
        return f"read_page|{path}|offset={offset}"
    if tool_name == "query_graph":
        question = str(args.get("question", "")).lower().strip()
        return f"query_graph|{question}"
    return f"{tool_name}|{json.dumps(args, sort_keys=True, default=str)}"


# ── 反思上下文构建 ────────────────────────────────────────────────────────────


def _format_reflection_context(recent_msgs: list, poor_tools: list[str]) -> str:
    """构建反思节点的分析上下文文本

    从最近几轮消息中提取工具调用和结果，供 LLM 评估推理方向。

    Args:
        recent_msgs: 最近的 BaseMessage 列表
        poor_tools: 质量差的工具名列表

    Returns:
        格式化后的分析文本
    """
    parts: list[str] = []
    for m in recent_msgs:
        role = getattr(m, "type", "unknown")
        content = getattr(m, "content", "") or ""
        if isinstance(content, str) and content.strip():
            display = content[:300].replace("\n", " ")
            parts.append(f"[{role}]: {display}")

    parts.append(f"\n质量差的工具调用: {', '.join(poor_tools) if poor_tools else '无'}")

    return "\n".join(parts)

llm = ChatOpenAI(
    model=os.environ.get(C.ENV_DEEPSEEK_MODEL, C.DEFAULT_MODEL),
    api_key=os.environ[C.ENV_DEEPSEEK_API_KEY],
    base_url=os.environ.get(C.ENV_DEEPSEEK_API_BASE, C.DEFAULT_API_BASE),
    timeout=C.LLM_TIMEOUT,
    max_retries=C.LLM_MAX_RETRIES,
)
llm_with_tools = registry.bind_tools(llm)

# ── 摘要压缩专用 LLM（小模型） ──────────────────────────────────────────────

# 固定使用 DeepSeek v4 Flash，配置项可在项目级 .env 中覆盖
# 单独实例避免阻塞主 LLM：压缩请求不会占用主模型配额
summarizer_llm = ChatOpenAI(
    model=os.environ.get(C.ENV_SUMMARIZER_MODEL, C.DEFAULT_SUMMARIZER_MODEL),
    api_key=os.environ.get(C.ENV_SUMMARIZER_API_KEY) or os.environ[C.ENV_DEEPSEEK_API_KEY],
    base_url=os.environ.get(C.ENV_SUMMARIZER_API_BASE) or os.environ.get(C.ENV_DEEPSEEK_API_BASE, C.DEFAULT_API_BASE),
    timeout=int(os.environ.get(C.ENV_SUMMARIZER_TIMEOUT, C.DEFAULT_SUMMARIZER_TIMEOUT)),
    max_retries=int(os.environ.get(C.ENV_SUMMARIZER_MAX_RETRIES, C.DEFAULT_SUMMARIZER_MAX_RETRIES)),
)


# ── 工作记忆上下文构建 ────────────────────────────────────────────────────────


def _build_wm_context(working_memory: dict) -> str | None:
    """构建工作记忆上下文文本，供 LLM 注入

    将结构化的工作记忆槽位格式化为易读文本，
    作为 SystemMessage 注入 LLM 输入（不污染 state messages）。

    Args:
        working_memory: AgentState 中的 working_memory 字典

    Returns:
        格式化文本，无内容时返回 None
    """
    if not working_memory:
        return None

    parts: list[str] = []

    goal = working_memory.get(C.WM_SLOT_CURRENT_GOAL)
    if goal:
        parts.append(f"用户当前目标: {goal}")

    facts = working_memory.get(C.WM_SLOT_KEY_FACTS, [])
    if facts:
        fact_lines = "\n".join(f"- {f}" for f in facts[-10:])  # 仅注入最近的 10 条
        parts.append(f"已确认的关键事实:\n{fact_lines}")

    entities = working_memory.get(C.WM_SLOT_ENTITIES, [])
    if entities:
        parts.append("提及的知识库页面: " + ", ".join(entities[-15:]))

    identity = working_memory.get(C.WM_SLOT_USER_IDENTITY, {})
    if identity:
        info = ", ".join(f"{k}={v}" for k, v in identity.items())
        parts.append(f"用户信息: {info}")

    if not parts:
        return None

    return "【工作记忆】\n" + "\n\n".join(parts)


# ── 图节点 ────────────────────────────────────────────────────────────────────


def intent_classifier_node(state: AgentState) -> dict:
    """意图分类节点：分析用户最新输入，识别意图类别

    在每轮用户输入进入 agent 节点前运行。
    仅在以下情况执行实际分类：
      - state 中尚无 current_intent 字段（首轮）
      - 最新消息是 HumanMessage（用户新输入）

    工具调用循环中不重新分类（最新消息是 AIMessage/ToolMessage）。

    意图分类结果影响：
      - call_model 根据意图决定是否绑定工具
        问候/闲聊 → 不绑定工具（节省 token）
        知识查询 → 绑定工具
      - 意图信息注入 LLM 上下文（可选的 SystemMessage）

    Returns:
        {current_intent: {...}} 或 {}（不分类时）
    """
    messages = state.get(C.STATE_MESSAGES, [])
    if not messages:
        return {}

    # 仅当最新消息是用户输入时才分类
    last_msg = messages[-1]
    if not isinstance(last_msg, HumanMessage):
        logger.debug(C.LOG_INTENT_SKIP)
        return {}

    # 已分类且无新 HumanMessage → 跳过
    existing = state.get(C.STATE_INTENT)
    if existing and existing.get('category'):
        return {}

    text = str(last_msg.content) if last_msg.content else ''
    if not text:
        return {
            C.STATE_INTENT: {
                'category': C.INTENT_UNKNOWN,
                'confidence': 0.0,
                'explanation': '空输入',
            }
        }

    result = classify_intent(text)
    logger.info(C.LOG_INTENT_CLASSIFIED,
                result['category'], result['confidence'], text[:50])

    return {C.STATE_INTENT: result}


def call_model(state: AgentState) -> dict:
    """调 LLM，返回响应追加到 messages

    Attention Sink 集成：
      1. 从用户最新输入检测需要锚定的信息
      2. 将已有锚定知识注入 LLM 上下文（不污染消息历史）
      3. 返回更新后的锚定列表

    Working Memory 集成：
      4. 从 working_memory 字段构建上下文注入 LLM
    """
    messages = list(state[C.STATE_MESSAGES])
    existing_sinks = state.get(C.STATE_ATTENTION_SINKS, [])
    working_memory = state.get(C.STATE_WORKING_MEMORY, {}) or {}

    # 1. 检测 Attention Sink（从最后一轮用户输入）
    if messages and isinstance(messages[-1], HumanMessage):
        user_text = messages[-1].content or ""
        history_texts = [
            m.content for m in messages[-6:]  # 取最近几轮用于频次统计
            if isinstance(m, (HumanMessage, AIMessage)) and m.content
        ]
        updated_sinks = update_attention_sinks(user_text, existing_sinks, history_texts)
    else:
        updated_sinks = list(existing_sinks)

    # 2. 构建 LLM 输入（注入上下文，不污染消息历史）
    llm_messages = list(messages)

    # 2a. 注入 Attention Sink 知识
    if updated_sinks:
        sink_knowledge = format_sink_knowledge(updated_sinks)
        if sink_knowledge:
            sink_msg = SystemMessage(content=sink_knowledge)
            insert_idx = 1 if llm_messages and isinstance(llm_messages[0], SystemMessage) else 0
            llm_messages.insert(insert_idx, sink_msg)

    # 2b. 注入 Working Memory 上下文
    wm_context = _build_wm_context(working_memory)
    if wm_context:
        wm_msg = SystemMessage(content=wm_context)
        # 在 sink 消息之后插入（如果两者都有，sink 优先）
        if llm_messages and isinstance(llm_messages[0], SystemMessage):
            llm_messages.insert(1, wm_msg)
        else:
            llm_messages.insert(0, wm_msg)

    # 2c. 注入意图上下文（让 LLM 知道用户的意图分类）
    current_intent = state.get(C.STATE_INTENT, {})
    if current_intent and current_intent.get('category'):
        intent_text = (
            f"【意图识别】用户意图: {current_intent['category']}"
            f" (置信度: {current_intent.get('confidence', 0):.1f})"
        )
        if current_intent.get('explanation'):
            intent_text += f" - {current_intent['explanation']}"
        intent_msg = SystemMessage(content=intent_text)
        # 在 sink 和 wm 之后插入
        insert_pos = len(llm_messages) - len(messages)
        if insert_pos > 0 and insert_pos <= len(llm_messages):
            llm_messages.insert(insert_pos, intent_msg)

    # 3. 步数计数（Self-Correction 熔断器）
    current_step = state.get(C.STATE_STEP_COUNT, 0)
    result_step = current_step + 1
    logger.debug("推理步数 | step=%d/%d", result_step, C.MAX_STEPS)

    # 4. 意图感知的 LLM 调用
    # 问候/闲聊 → 不绑定工具（节省 token，避免不必要的工具调用）
    no_tool_intents = {C.INTENT_GREETING, C.INTENT_CHIT_CHAT}
    if current_intent.get('category') in no_tool_intents:
        logger.debug("意图=%s → 跳过工具绑定", current_intent['category'])
        response = llm.invoke(llm_messages)
    else:
        response = llm_with_tools.invoke(llm_messages)

    result: dict = {
        C.STATE_MESSAGES: [response],
        C.STATE_STEP_COUNT: result_step,
    }
    if updated_sinks:
        result[C.STATE_ATTENTION_SINKS] = updated_sinks
    return result


tool_node = ToolNode(registry.list_enabled())


def should_continue(state: AgentState) -> Literal["validate_tool", "summarizer"]:
    """判断 LLM 输出是否需要执行工具——图分支路由函数

    ReAct + Self-Correction 第一层防御入口：
      - 有 tool_calls → validate_tool 节点（步数熔断 + 去重 + 置信度）
      - 无 tool_calls → summarizer 节点（压缩后结束）
    """
    last_msg = state[C.STATE_MESSAGES][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return C.NODE_VALIDATE_TOOL
    return C.NODE_SUMMARIZER


def human_approval_node(state: AgentState) -> dict:
    """人工审批节点：工具调用前暂停，等待用户批准或拒绝

    通过 interrupt() 暂停图执行。用户审批结果通过 Command(resume=...) 恢复。
    批准后 → 状态不变 → should_after_approval 路由到 tools 节点
    拒绝后 → 追加拒绝 ToolMessage → should_after_approval 路由回 agent 节点
    """
    last_msg = state[C.STATE_MESSAGES][-1]
    tool_calls = getattr(last_msg, "tool_calls", [])
    if not tool_calls:
        return {}

    # 暂停图，等待人工审批
    approval = interrupt({
        "question": "是否批准以下工具调用？",
        C.FIELD_TOOL_CALLS: [
            {"name": tc["name"], "args": tc["args"], "id": tc["id"]}
            for tc in tool_calls
        ],
    })

    if approval and approval.get(C.FIELD_APPROVAL):
        # 批准：不修改状态，后续 should_after_approval 路由到 tools
        logger.info(C.LOG_APPROVAL_RESUMED, "approve", "approved")
        return {}

    # 拒绝：为每个 tool_call 创建拒绝的 ToolMessage
    logger.info(C.LOG_APPROVAL_RESUMED, "approve", "rejected")
    rejection_msgs = []
    for tc in tool_calls:
        rejection_msgs.append(ToolMessage(
            content="用户拒绝执行此工具调用。请基于已有知识回答，或告知用户需要数据但被拒绝。",
            tool_call_id=tc["id"],
        ))
    return {C.STATE_MESSAGES: rejection_msgs}


def should_after_approval(state: AgentState) -> Literal["tools", "agent"]:
    """审批后的路由决策

    当 human_approval_node 返回 {}（批准）时，最后一条消息仍是含 tool_calls 的 AIMessage
    当 human_approval_node 返回 rejection ToolMessages 时，最后一条是 ToolMessage（无 tool_calls）
    """
    last_msg = state[C.STATE_MESSAGES][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return C.NODE_TOOLS  # 批准 → 执行工具
    return C.NODE_AGENT  # 拒绝 → 返回 agent 让 LLM 处理拒绝结果


# ── 自修正：前置校验节点（步数熔断 + 动作去重 + 置信度） ─────────────────


def should_after_validate(state: AgentState) -> Literal["approve", "agent", "summarizer"]:
    """校验后路由决策（Self-Correction 第一层）

    从 self_correction 读取校验结果：
      - step_limit_reached → summarizer（强制输出当前最优解后结束）
      - correction_reason 存在 → agent（带着校验消息回 agent 重新思考）
      - validated=True → approve（通过校验，进入人工审批）

    Returns:
        "approve" — 校验通过，进入人工审批
        "agent" — 需要重新思考（重复/低置信）
        "summarizer" — 步数超限，强制结束
    """
    sc = state.get(C.STATE_SELF_CORRECTION, {}) or {}
    if sc.get(C.SC_FIELD_STEP_LIMIT):
        return C.NODE_SUMMARIZER
    if sc.get(C.SC_FIELD_CORRECTION_REASON):
        return C.NODE_AGENT
    return C.NODE_APPROVE


def validate_tool_node(state: AgentState) -> dict:
    """工具调用前置校验节点——步数熔断 + 动作去重

    ReAct + Self-Correction 第一层防御。

    三种阻断场景：
      1. 步数超限 → 注入 ToolMessage 告知 LLM 已到达限制，
         should_after_validate 路由到 summarizer（强制输出当前最优解后结束）
      2. 重复动作 → 注入 ToolMessage 告知 LLM （工具 + 参数）已执行过且结果不佳，
         should_after_validate 路由回 agent 重新思考
      3. 全部通过 → 设置 self_correction.validated=True，
         should_after_validate 路由到 approve（人工审批）

    Returns:
        dict: 阻断时注入 ToolMessage + self_correction 标记；
              放行时仅设 validated=True
    """
    messages = state[C.STATE_MESSAGES]
    step_count = state.get(C.STATE_STEP_COUNT, 0)
    executed = state.get(C.STATE_EXECUTED_ACTIONS, {}) or {}

    last_msg = messages[-1]
    tool_calls = getattr(last_msg, "tool_calls", [])
    if not tool_calls:
        return {C.STATE_SELF_CORRECTION: {C.SC_FIELD_VALIDATED: True}}

    # ── 1. 步数熔断 ─────────────────────────────────────────────────────
    if step_count >= C.MAX_STEPS:
        logger.warning(C.LOG_STEP_LIMIT_EXCEEDED, step_count, C.MAX_STEPS)
        # 注入 ToolMessage：告知 LLM 已到达限制，应基于已有信息回答
        first_tc_id = tool_calls[0]["id"]
        limit_msg = ToolMessage(
            content=f"【步数限制】已到达最大推理步数限制（{C.MAX_STEPS} 步）。"
                    "请基于当前已有信息直接回答用户问题，不要再调用新工具。",
            tool_call_id=first_tc_id,
        )
        return {
            C.STATE_MESSAGES: [limit_msg],
            C.STATE_SELF_CORRECTION: {C.SC_FIELD_STEP_LIMIT: True},
        }

    # ── 2. 动作去重 ─────────────────────────────────────────────────────
    for tc in tool_calls:
        action_key = _make_action_key(tc["name"], tc.get("args", {}))
        if action_key in executed:
            existing = executed[action_key]
            # 仅当之前的结果质量差时才阻止
            if existing.get("quality") in ("poor", "error"):
                logger.warning(C.LOG_DUPLICATE_ACTION, tc["name"], action_key)
                rejection = ToolMessage(
                    content=f"【重复检测】工具 {tc['name']} 使用参数 {tc.get('args', {})} "
                            "在上一步已执行过且未得到有用结果，请换一种搜索策略或关键词。",
                    tool_call_id=tc["id"],
                )
                return {
                    C.STATE_MESSAGES: [rejection],
                    C.STATE_SELF_CORRECTION: {
                        C.SC_FIELD_CORRECTION_REASON: C.SC_FIELD_CORRECTION_TYPE_DUP,
                    },
                }

    # ── 3. 全部通过 ─────────────────────────────────────────────────────
    logger.info(C.LOG_VALIDATE_PASS, len(tool_calls))
    return {C.STATE_SELF_CORRECTION: {C.SC_FIELD_VALIDATED: True}}


def summarizer_node(state: AgentState) -> dict:
    """对话摘要压缩节点

    在 agent 返回回答（无 tool_calls）后执行。
    当对话历史超过 SUMMARIZE_THRESHOLD 时，将早期对话压缩为 LLM 生成的摘要，
    用 RemoveMessage 移除旧消息并用一条 SystemMessage 摘要取代。

    Attention Sink 集成：
      摘要生成时注入锚定上下文，确保关键信息在摘要中得到保留。

    Working Memory 集成：
      将工作记忆中的关键事实注入摘要 prompt，确保不被压缩丢弃。

    Returns:
        {"messages": [RemoveMessage(id=...), SystemMessage(摘要)]} 或 {}
    """
    messages = state[C.STATE_MESSAGES]
    sinks = state.get(C.STATE_ATTENTION_SINKS, [])
    working_memory = state.get(C.STATE_WORKING_MEMORY, {}) or {}

    # 将锚定知识注入摘要的 prompt context
    sink_context = extract_sink_content(sinks) if sinks else ""

    # 将工作记忆中的关键事实也注入 context
    wm_facts = working_memory.get(C.WM_SLOT_KEY_FACTS, [])
    if wm_facts:
        fact_text = "已知事实: " + "; ".join(wm_facts[:10])
        sink_context = (sink_context + "\n" + fact_text) if sink_context else fact_text

    remove_ops, summary_msg = condense_history(messages, summarizer_llm, sink_context=sink_context)
    if not remove_ops:
        return {}  # 无需压缩

    result: dict = {C.STATE_MESSAGES: remove_ops + [summary_msg]}
    # 锚定信息和工作记忆在 messages 字段之外单独存在，不受 RemoveMessage 影响
    if sinks:
        result[C.STATE_ATTENTION_SINKS] = sinks
    if working_memory:
        result[C.STATE_WORKING_MEMORY] = working_memory
    return result


# ── 自修正：后置验证节点（工具结果质量检查 + 动作记录） ──────────────────


def should_after_verify(state: AgentState) -> Literal["agent", "reflect_node"]:
    """验证后路由决策（Self-Correction 第二层）

    从 self_correction 读取验证结果：
      - poor_result → reflect_node（结果质量差，需要反思修正）
      - verified → agent（验证通过，继续下一轮推理）

    Returns:
        "agent" — 验证通过，继续推理
        "reflect_node" — 结果质量差，触发反思
    """
    sc = state.get(C.STATE_SELF_CORRECTION, {}) or {}
    if sc.get(C.SC_FIELD_POOR_RESULT):
        return C.NODE_REFLECT
    return C.NODE_AGENT


def verify_result_node(state: AgentState) -> dict:
    """工具结果后置验证节点

    ReAct + Self-Correction 第二层防御。

    验证维度：
      1. 空结果检测（search 返回 "未找到匹配" / read 返回空内容）
      2. 错误结果检测（返回 "失败" / "Error" 等前缀）
      3. 动作执行记录写入 executed_actions（供 validate_tool 去重使用）

    质量差时设置 self_correction.poor_result 标记，
    should_after_verify 路由到 reflect_node 做推理反思。

    Returns:
        dict: 更新 executed_actions + self_correction
    """
    messages = state[C.STATE_MESSAGES]
    executed = dict(state.get(C.STATE_EXECUTED_ACTIONS, {}) or {})

    # 找最近的含 tool_calls 的 AIMessage（获取工具名和参数）
    last_tc_ai: AIMessage | None = None
    last_tc_idx = -1
    for i, m in enumerate(reversed(messages)):
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            last_tc_ai = m
            last_tc_idx = len(messages) - 1 - i
            break

    if last_tc_ai is None:
        # 没有工具调用，无需验证
        return {C.STATE_SELF_CORRECTION: {C.SC_FIELD_VERIFIED: True}}

    # 构建 tool_call_id → 工具信息映射
    tc_map: dict[str, dict] = {}
    for tc in last_tc_ai.tool_calls:
        tc_map[tc["id"]] = {"name": tc["name"], "args": tc.get("args", {})}

    # 收集该轮工具调用的 ToolMessage（紧跟 AIMessage 之后）
    current_tool_msgs = [
        m for m in messages[last_tc_idx + 1:]
        if isinstance(m, ToolMessage)
    ]

    poor_tools: list[str] = []

    for tm in current_tool_msgs:
        tc_id = tm.tool_call_id
        tc_info = tc_map.get(tc_id, {})
        tool_name = tc_info.get("name", "unknown")
        tool_args = tc_info.get("args", {})
        content = str(tm.content) if tm.content else ""

        # 质量判断
        is_empty = (
            not content
            or content.strip() in (C.NO_MATCHES_MESSAGE, C.EMPTY_CONTENT_MESSAGE)
        )
        is_error = (
            content.startswith(("错误:", "失败:", "Error:", "error:", "路径越权", "页面不存在"))
            or "失败" in content[:30]
        )

        quality = "good"
        if is_error:
            quality = "error"
        elif is_empty:
            quality = "poor"
        else:
            quality = "good"

        if quality != "good":
            poor_tools.append(tool_name)

        # 记录已执行动作（标准化的 action_key）
        action_key = _make_action_key(tool_name, tool_args)
        # 只在尚不存在或之前的质量更差时更新
        if action_key not in executed or executed[action_key].get("quality") == "error":
            executed[action_key] = {
                "tool": tool_name,
                "args": tool_args,
                "result_truncated": content[:300],
                "quality": quality,
                "timestamp": time.time(),
            }

    update: dict = {C.STATE_EXECUTED_ACTIONS: executed}

    if poor_tools:
        update[C.STATE_SELF_CORRECTION] = {
            C.SC_FIELD_POOR_RESULT: True,
            C.SC_FIELD_POOR_TOOLS: poor_tools,
        }
        logger.warning(C.LOG_VERIFY_POOR_RESULT, poor_tools)
    else:
        update[C.STATE_SELF_CORRECTION] = {C.SC_FIELD_VERIFIED: True}
        logger.info(C.LOG_VERIFY_PASS, len(current_tool_msgs))

    return update


# ── 自修正：推理反思节点 ──────────────────────────────────────────────────


def reflect_node(state: AgentState) -> dict:
    """推理反思节点

    ReAct + Self-Correction 第三层防御。
    当工具返回空/错误结果时触发，用 LLM 评估上一步推理方向并给出修正策略。

    执行流程：
      1. 提取最近几轮对话作为反思上下文
      2. 用结构化 LLM 调用得到 verdict（proceed/revise）
      3. 如果 verdict=revise，注入 AIMessage 作为自我修正后的新计划
      4. 路由到 agent 节点按修正计划重新推理

    Returns:
        dict: 注入自我修正 AIMessage（如需）+ self_correction 标记
    """
    messages = state[C.STATE_MESSAGES]
    correction = state.get(C.STATE_SELF_CORRECTION, {}) or {}
    poor_tools = correction.get(C.SC_FIELD_POOR_TOOLS, [])

    # 提取最近上下文用于反思（最近 6 条消息）
    recent_msgs = messages[-6:]

    # 构建反思输入
    reflection_input = _format_reflection_context(recent_msgs, poor_tools)

    try:
        structured_llm = llm.with_structured_output(ReflectionResult)
        result = structured_llm.invoke([
            SystemMessage(content=REFLECTION_SYSTEM_PROMPT),
            HumanMessage(content=reflection_input),
        ])
        logger.info(C.LOG_REFLECTION, result.verdict)

        update: dict = {
            C.STATE_SELF_CORRECTION: {
                C.SC_FIELD_VERDICT: result.verdict,
            },
        }

        # 修正策略：注入自我修正消息作为下一轮 agent 的输入
        if result.verdict == C.SC_FIELD_VERDICT_REVISE and result.revised_plan.strip():
            correction_msg = AIMessage(
                content=(
                    f"【自我修正】上一步的搜索策略效果不佳。"
                    f"我重新评估了情况，修正后的搜索计划如下：\n{result.revised_plan}\n\n"
                    "我会按新方案继续查找相关信息。"
                )
            )
            update[C.STATE_MESSAGES] = [correction_msg]

        return update

    except Exception as e:
        logger.warning("反思节点调用失败 | error=%s", e)
        # 反思失败不阻断流程——默认 proceed，让 agent 继续
        return {
            C.STATE_SELF_CORRECTION: {
                C.SC_FIELD_VERDICT: C.SC_FIELD_VERDICT_PROCEED,
            },
        }


# ── 工作记忆提取节点 ──────────────────────────────────────────────────────────


def extract_wm_node(state: AgentState) -> dict:
    """从最新 LLM 回复中提取关键信息到工作记忆

    在 call_model 之后运行，解析 AI 回复：
      1. 提取引用的 Wiki 页面路径 → entities_mentioned
      2. 提取用户最新问题 → current_goal
      3. 提取关键事实片段 → key_facts（简化实现）

    Returns:
        {"working_memory": {...}} 或 {}（无更新时）
    """
    wm = state.get(C.STATE_WORKING_MEMORY, {}) or {}
    messages = state[C.STATE_MESSAGES]
    if not messages:
        return {}

    update: dict = {}

    # 1. 从 AI 回复中提取引用的 Wiki 页面
    ai_msgs = [
        m for m in reversed(messages)
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None)
    ]
    if ai_msgs:
        content = str(ai_msgs[0].content)
        pages = re.findall(C.WIKI_PATH_REGEX, content)
        if pages:
            existing = wm.get(C.WM_SLOT_ENTITIES, [])
            update[C.WM_SLOT_ENTITIES] = list(dict.fromkeys(existing + pages))

    # 2. 提取用户最新问题作为 current_goal 线索
    for m in reversed(messages):
        if hasattr(m, "type") and m.type == "human":
            content = getattr(m, "content", "")
            if isinstance(content, str) and len(content) > 5:
                new_goal = content[:200]
                previous_goal = wm.get(C.WM_SLOT_CURRENT_GOAL, "")
                if new_goal != previous_goal:
                    update[C.WM_SLOT_CURRENT_GOAL] = new_goal
            break

    if not update:
        logger.debug("extract_wm: 无新信息提取")
        return {}

    logger.info("工作记忆更新 | slots=%s", list(update.keys()))
    return {C.STATE_WORKING_MEMORY: update}


# ── 工作记忆维护节点（槽级压缩） ──────────────────────────────────────────────


def wm_eviction_node(state: AgentState) -> dict:
    """工作记忆维护：槽级压缩与清理

    在 extract_wm 之后运行，按优先级策略清理低价值槽位：
      1. entities_mentioned: 超过上限时保留最新的
      2. tool_cache: 超过上限时丢弃最旧的
      3. key_facts: case-insensitive dedup

    Returns:
        {"working_memory": {...}} 或 {}（无变更）
    """
    wm = state.get(C.STATE_WORKING_MEMORY, {}) or {}
    if not wm:
        return {}

    changed = False

    # 1. entities_mentioned: case-insensitive dedup
    entities = wm.get(C.WM_SLOT_ENTITIES, [])
    if len(entities) != len({e.lower() for e in entities}):
        seen: set[str] = set()
        deduped: list[str] = []
        for e in entities:
            key = e.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(e)
        wm[C.WM_SLOT_ENTITIES] = deduped[:C.WM_MAX_ENTITIES]
        changed = True

    # 2. key_facts: trim to max (redundant with reducer, safety net)
    facts = wm.get(C.WM_SLOT_KEY_FACTS, [])
    if len(facts) > C.WM_MAX_FACTS:
        wm[C.WM_SLOT_KEY_FACTS] = facts[-C.WM_MAX_FACTS:]
        changed = True

    # 3. tool_cache: 丢弃空值或无效条目
    cache = wm.get(C.WM_SLOT_TOOL_CACHE, {})
    if cache:
        cleaned = {k: v for k, v in cache.items() if v}
        if len(cleaned) != len(cache):
            wm[C.WM_SLOT_TOOL_CACHE] = cleaned
            changed = True

    if not changed:
        return {}

    logger.debug("工作记忆维护 | entities=%d facts=%d cache=%d",
                 len(wm.get(C.WM_SLOT_ENTITIES, [])),
                 len(wm.get(C.WM_SLOT_KEY_FACTS, [])),
                 len(wm.get(C.WM_SLOT_TOOL_CACHE, {})))
    return {C.STATE_WORKING_MEMORY: wm}


# ── 图构建（ReAct + Self-Correction 架构） ──────────────────────────────

# 三层自修正链路：
#   ① validate_tool  — 执行前：步数熔断 + 动作去重
#   ② verify_result  — 执行后：工具结果质量检查 + 动作记录
#   ③ reflect_node   — 推理反思：LLM 评估方向 + 修正策略

builder = StateGraph(AgentState)
builder.add_node(C.NODE_INTENT_CLASSIFIER, intent_classifier_node)  # 前置意图分类
builder.add_node(C.NODE_AGENT, call_model)
builder.add_node(C.NODE_EXTRACT_WM, extract_wm_node)
builder.add_node(C.NODE_WM_EVICTION, wm_eviction_node)
builder.add_node(C.NODE_VALIDATE_TOOL, validate_tool_node)    # ① 前置校验
builder.add_node(C.NODE_APPROVE, human_approval_node)
builder.add_node(C.NODE_TOOLS, tool_node)
builder.add_node(C.NODE_VERIFY_RESULT, verify_result_node)    # ② 后置验证
builder.add_node(C.NODE_REFLECT, reflect_node)                # ③ 推理反思
builder.add_node(C.NODE_SUMMARIZER, summarizer_node)
builder.set_entry_point(C.NODE_INTENT_CLASSIFIER)

# 推理链路
builder.add_edge(C.NODE_INTENT_CLASSIFIER, C.NODE_AGENT)          # intent_classifier → agent
builder.add_edge(C.NODE_AGENT, C.NODE_EXTRACT_WM)                # agent → extract_wm
builder.add_edge(C.NODE_EXTRACT_WM, C.NODE_WM_EVICTION)         # extract_wm → wm_eviction

# ① 第一层防御：wm_eviction → (有 tool_calls → validate_tool | 无 → summarizer)
builder.add_conditional_edges(C.NODE_WM_EVICTION, should_continue)

# validate_tool → (通过 → approve | 阻断 → agent | 超限 → summarizer)
builder.add_conditional_edges(C.NODE_VALIDATE_TOOL, should_after_validate)

# approve → (批准 → tools | 拒绝 → agent)
builder.add_conditional_edges(C.NODE_APPROVE, should_after_approval)

# ② 第二层防御：tools → verify_result (非直接回 agent)
builder.add_edge(C.NODE_TOOLS, C.NODE_VERIFY_RESULT)

# verify_result → (有效 → agent | 差 → reflect_node)
builder.add_conditional_edges(C.NODE_VERIFY_RESULT, should_after_verify)

# ③ 第三层防御：reflect_node → agent（修正后重试）
builder.add_edge(C.NODE_REFLECT, C.NODE_AGENT)

# 结束
builder.add_edge(C.NODE_SUMMARIZER, END)

# 持久化 checkpointer
from src.agent.memory.store import migrate_memorysaver_to_sqlite  # noqa: E402
migrate_memorysaver_to_sqlite()

app = builder.compile(checkpointer=MemorySaver())


def build_agent() -> CompiledStateGraph:
    """构建 ReAct Agent（CompiledStateGraph）"""
    logger.info(C.LOG_AGENT_BUILT, registry.list_enabled_names())
    return app
