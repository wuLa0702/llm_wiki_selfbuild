"""
规划模块 — LangGraph 图构建 + 节点函数 + 路由逻辑

职责：
  - 定义 AgentState 状态类型
  - 初始化 LLM（支持 DeepSeek / OpenAI 兼容 API）
  - 绑定工具到 LLM
  - 构建 LangGraph StateGraph（节点、边、条件路由）
  - 提供 build_agent() 接口供编排层调用

节点流程：
  agent → (有 tool_calls → approve, 无 → summarizer)
  approve → (批准 → tools, 拒绝 → agent)
  tools → agent
  summarizer → __end__
"""

import logging
import os
import re
from typing import Annotated, Any, Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, RemoveMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt

from src.agent import constants as C
from src.agent.action.tools import read_page, search_wiki
from src.agent.memory.attention import extract_sink_content, format_sink_knowledge, update_attention_sinks
from src.agent.memory.summarizer import condense_history
from src.agent.planning.prompt import SYSTEM_PROMPT

load_dotenv()
logger = logging.getLogger("agent.graph")


# ── 工具列表 ──────────────────────────────────────────────────────────────────

P1_TOOLS = [search_wiki, read_page]


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
    """
    messages: Annotated[list[BaseMessage], add_messages]
    attention_sinks: list[dict]
    working_memory: Annotated[dict[str, Any], working_memory_reducer]


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


# ── LLM 初始化 ────────────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model=os.environ.get(C.ENV_DEEPSEEK_MODEL, C.DEFAULT_MODEL),
    api_key=os.environ[C.ENV_DEEPSEEK_API_KEY],
    base_url=os.environ.get(C.ENV_DEEPSEEK_API_BASE, C.DEFAULT_API_BASE),
    timeout=C.LLM_TIMEOUT,
    max_retries=C.LLM_MAX_RETRIES,
)
llm_with_tools = llm.bind_tools(P1_TOOLS)

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

    # 3. 调用 LLM
    response = llm_with_tools.invoke(llm_messages)

    result: dict = {C.STATE_MESSAGES: [response]}
    if updated_sinks:
        result[C.STATE_ATTENTION_SINKS] = updated_sinks
    return result


tool_node = ToolNode(P1_TOOLS)


def should_continue(state: AgentState) -> Literal["approve", "summarizer"]:
    """判断 LLM 输出是否需要执行工具——图分支路由函数

    路由规则：
      - 有 tool_calls → approve 节点（人工审批）
      - 无 tool_calls → summarizer 节点（压缩后结束）
    """
    last_msg = state[C.STATE_MESSAGES][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return C.NODE_APPROVE
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


# ── 图构建 ────────────────────────────────────────────────────────────────────

builder = StateGraph(AgentState)
builder.add_node(C.NODE_AGENT, call_model)
builder.add_node(C.NODE_EXTRACT_WM, extract_wm_node)
builder.add_node(C.NODE_WM_EVICTION, wm_eviction_node)
builder.add_node(C.NODE_APPROVE, human_approval_node)
builder.add_node(C.NODE_TOOLS, tool_node)
builder.add_node(C.NODE_SUMMARIZER, summarizer_node)
builder.set_entry_point(C.NODE_AGENT)
builder.add_edge(C.NODE_AGENT, C.NODE_EXTRACT_WM)       # agent → extract_wm
builder.add_edge(C.NODE_EXTRACT_WM, C.NODE_WM_EVICTION)  # extract_wm → wm_eviction
builder.add_conditional_edges(C.NODE_WM_EVICTION, should_continue)  # wm_eviction → (approve | summarizer)
builder.add_edge(C.NODE_TOOLS, C.NODE_AGENT)
builder.add_edge(C.NODE_SUMMARIZER, END)
builder.add_conditional_edges(C.NODE_APPROVE, should_after_approval)

# 持久化 checkpointer
from src.agent.memory.store import migrate_memorysaver_to_sqlite  # noqa: E402
migrate_memorysaver_to_sqlite()

app = builder.compile(checkpointer=MemorySaver())


def build_agent() -> CompiledStateGraph:
    """构建 ReAct Agent（CompiledStateGraph）"""
    logger.info(C.LOG_AGENT_BUILT, [t.name for t in P1_TOOLS])
    return app
