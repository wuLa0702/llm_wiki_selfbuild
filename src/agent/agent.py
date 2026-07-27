"""
Agent 构建 + 流式对话接口

导出接口:
  build_agent() -> CompiledStateGraph
  chat_stream(messages) -> AsyncIterator[dict]
  chat_stream_session(content, thread_id) -> AsyncIterator[dict]

接口固定，换 LLM Provider 或 LangGraph 版本时路由层和前端不改。
"""

import json
import logging
import os
import re
from collections.abc import AsyncIterator
from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from src.agent import constants as C
from src.agent import persistence as P
from src.agent.summarizer import condense_history
from src.agent.tools import read_page, search_wiki

load_dotenv()
logger = logging.getLogger("agent")


# ── 系统提示 ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是 LLM Wiki 的知识助手。你可以搜索、阅读、分析知识库中的内容来回答用户问题。

规则：
1. 回答必须基于 Wiki 页面内容，不要编造信息
2. 不确定时先调用 search_wiki 找到相关页面，再用 read_page 获取详情
3. 引用页面时使用 [[页面路径]] 格式，用户可点击跳转
4. 如果知识库中没有相关内容，明确告知用户，不要编造
5. 使用中文回答（除非用户用其他语言提问）
6. 回答要简洁准确，适当使用 Markdown 格式"""


# ── 工具列表 ──────────────────────────────────────────────────────────────────

P1_TOOLS = [search_wiki, read_page]


# ── 图状态定义 ────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """LangGraph 图共享状态

    messages: 对话 + 工具调用全链路记录
    使用 add_messages reducer 支持增量追加（非覆盖），
    这是多轮会话隔离的基础——Checkpointer 按 thread_id 持久化后，
    每轮只传新消息即可自动合并历史。
    """
    messages: Annotated[list[BaseMessage], add_messages]


# ── 结构化输出模型 ────────────────────────────────────────────────────────────


class AgentResponse(BaseModel):
    """Agent 最终回答的结构化输出

    当 LLM 不调用工具、直接回答时，
    用 with_structured_output 提取引用页面和追问建议。
    """
    answer: str = Field(description="Agent 的回答正文")
    cited_pages: list[str] = Field(description="回答中引用的 Wiki 页面路径列表", default=[])
    follow_up_questions: list[str] = Field(description="基于当前回答建议的追问话题", default=[])


# ── LLM 初始化 ────────────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model=os.environ.get(C.ENV_DEEPSEEK_MODEL, C.DEFAULT_MODEL),
    api_key=os.environ[C.ENV_DEEPSEEK_API_KEY],
    base_url=os.environ.get(C.ENV_DEEPSEEK_API_BASE, C.DEFAULT_API_BASE),
    timeout=C.LLM_TIMEOUT,
    max_retries=C.LLM_MAX_RETRIES,
)
llm_with_tools = llm.bind_tools(P1_TOOLS)


# ── 图节点 ────────────────────────────────────────────────────────────────────

def call_model(state: AgentState) -> dict:
    """调 LLM，返回响应追加到 messages"""
    response = llm_with_tools.invoke(state[C.STATE_MESSAGES])
    return {C.STATE_MESSAGES: [response]}


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
    低于阈值时无操作，直接返回空 dict。

    Returns:
        {"messages": [RemoveMessage(id=...), SystemMessage(摘要)]} 或 {}
    """
    remove_ops, summary_msg = condense_history(state[C.STATE_MESSAGES], llm)
    if not remove_ops:
        return {}  # 无需压缩

    # add_messages 处理: RemoveMessage 移除旧消息 → 新摘要 SystemMessage 加入
    return {C.STATE_MESSAGES: remove_ops + [summary_msg]}


# ── 结构化 LLM 实例 ──────────────────────────────────────────────────────────
# 专用于结构化输出（with_structured_output），与工具绑定的 llm_with_tools 分开

STRUCTURED_EXTRACTION_SYSTEM_PROMPT = (
    "从以下 Agent 回答中提取：\n"
    "1. 引用的 Wiki 页面路径（格式如 entities/python.md）\n"
    "2. 建议的追问问题\n\n"
    "如果回答中没有引用任何页面，cited_pages 返回空列表。"
    "如果没有明显的追问方向，follow_up_questions 返回空列表。"
)


def format_response(content: str) -> AgentResponse:
    """对 Agent 的文本回答做结构化提取

    在 agent 回答后用 with_structured_output 提取 cited_pages 和 follow_up_questions。
    提取失败时降级为仅保留 answer 文本。

    Args:
        content: Agent 的 AIMessage.content

    Returns:
        AgentResponse(answer, cited_pages, follow_up_questions)
    """
    from langchain_core.messages import HumanMessage, SystemMessage as SysMsg

    try:
        structured_llm = llm.with_structured_output(AgentResponse)
        result = structured_llm.invoke([
            SysMsg(content=STRUCTURED_EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=content),
        ])
        return result
    except Exception as e:
        logger.warning("Agent 响应结构化提取失败 | error=%s", e)
        return AgentResponse(answer=content, cited_pages=[], follow_up_questions=[])


# ── 图构建 ────────────────────────────────────────────────────────────────────

builder = StateGraph(AgentState)
builder.add_node(C.NODE_AGENT, call_model)
builder.add_node(C.NODE_APPROVE, human_approval_node)
builder.add_node(C.NODE_TOOLS, tool_node)
builder.add_node(C.NODE_SUMMARIZER, summarizer_node)
builder.set_entry_point(C.NODE_AGENT)
builder.add_edge(C.NODE_TOOLS, C.NODE_AGENT)
builder.add_edge(C.NODE_SUMMARIZER, END)
builder.add_conditional_edges(C.NODE_AGENT, should_continue)
builder.add_conditional_edges(C.NODE_APPROVE, should_after_approval)

# ── 持久化 Checkpointer ───────────────────────────────────────────────────────
# MemorySaver 在运行时管理图状态（内存中）。
# 跨会话持久化由 persistence.py 的 SQLite 层在 chat_stream_session 中完成。
P.migrate_memorysaver_to_sqlite()

app = builder.compile(checkpointer=MemorySaver())


def build_agent() -> CompiledStateGraph:
    """构建 ReAct Agent（CompiledStateGraph）"""
    logger.info(C.LOG_AGENT_BUILT, [t.name for t in P1_TOOLS])
    return app


# ── 事件处理辅助函数 ──────────────────────────────────────────────────────────

def _extract_event(event: dict) -> tuple[str, str, dict]:
    """解构 astream_events 事件为 (kind, name, data) 三元组"""
    return (
        event.get(C.FIELD_EVENT, ""),
        event.get(C.FIELD_NAME, ""),
        event.get(C.FIELD_DATA, {}),
    )


def _emit_token(chunk) -> dict | None:
    """从 astream_events chunk 中提取 token 事件，无内容返回 None"""
    if chunk is None:
        return None
    content = getattr(chunk, C.FIELD_CONTENT, "")
    if not content:
        return None
    return {C.FIELD_TYPE: C.EVENT_TOKEN, C.FIELD_CONTENT: content}


# ── 流式对话接口 ──────────────────────────────────────────────────────────────

async def chat_stream(
    agent: CompiledStateGraph,
    messages: list[dict],
) -> AsyncIterator[dict]:
    """流式对话接口 —— 生产 SSE 事件

    Args:
        agent: build_agent() 返回的 CompiledStateGraph 实例
        messages: [{"role": "user"|"assistant"|"system", "content": "..."}, ...]

    Yields:
        {"type": "token", "content": "..."}      — LLM token 级输出
        {"type": "tool_start", "tool": "...", "input": {...}}  — 工具调用开始
        {"type": "tool_end", "tool": "...", "output": "..."}   — 工具调用结束
        {"type": "done", "sources": [...]}        — 对话结束，返回引用来源
        {"type": "error", "message": "..."}       — 错误事件
    """
    # 消息格式转换：dict → LangChain Message 对象
    lc_messages: list[BaseMessage] = []
    for msg in messages:
        role = msg.get(C.FIELD_ROLE, C.DEFAULT_ROLE)
        content = msg.get(C.FIELD_CONTENT, "")
        if role == C.ROLE_USER:
            lc_messages.append(HumanMessage(content=content))
        elif role == C.ROLE_ASSISTANT:
            lc_messages.append(AIMessage(content=content))
        elif role == C.ROLE_SYSTEM:
            lc_messages.append(SystemMessage(content=content))

    if not lc_messages:
        yield {C.FIELD_TYPE: C.EVENT_ERROR, C.FIELD_MESSAGE: C.ERROR_EMPTY_MESSAGES}
        return

    # 窗口截断：保留 SystemMessage（人格设定）+ 最近 C.MAX_MESSAGE_TURNS 轮对话
    system_msgs = [m for m in lc_messages if isinstance(m, SystemMessage)]
    non_system = [m for m in lc_messages if not isinstance(m, SystemMessage)]
    if len(non_system) > C.MAX_MESSAGE_TURNS:
        logger.warning(C.LOG_WINDOW_EXCEEDED, len(non_system), C.MAX_MESSAGE_TURNS)
        non_system = non_system[-C.MAX_MESSAGE_TURNS:]
    lc_messages = system_msgs + non_system

    wiki_path_source: list[str] = []

    try:
        async for event in agent.astream_events(
            {C.STATE_MESSAGES: lc_messages},
            version=C.ASTREAM_EVENTS_VERSION,
        ):
            kind, name, data = _extract_event(event)

            if kind == C.KIND_CHAT_MODEL_STREAM:
                token = _emit_token(data.get(C.FIELD_CHUNK))
                if token:
                    yield token

            elif kind == C.KIND_TOOL_START:
                yield {
                    C.FIELD_TYPE: C.EVENT_TOOL_START,
                    C.FIELD_TOOL: name,
                    C.FIELD_INPUT: data.get(C.FIELD_INPUT, {}),
                }

            elif kind == C.KIND_TOOL_END:
                output = data.get(C.FIELD_OUTPUT, "")
                output_str = str(output) if output else ""
                yield {
                    C.FIELD_TYPE: C.EVENT_TOOL_END,
                    C.FIELD_TOOL: name,
                    C.FIELD_OUTPUT: output_str[:C.TOOL_OUTPUT_DISPLAY_CHARS],
                }
                if output_str:
                    wiki_paths = re.findall(C.WIKI_PATH_REGEX, output_str)
                    wiki_path_source.extend(wiki_paths)

    except Exception as e:
        logger.error(C.LOG_STREAM_FAILED, e)
        yield {C.FIELD_TYPE: C.EVENT_ERROR, C.FIELD_MESSAGE: C.ERROR_AGENT_FAILED.format(e)}
        return

    yield {C.FIELD_TYPE: C.EVENT_DONE, C.FIELD_SOURCES: list(dict.fromkeys(wiki_path_source))}


# ── 多轮会话隔离接口 ──────────────────────────────────────────────────────────

def _serialize_messages(msgs: list[BaseMessage]) -> list[dict]:
    """将 BaseMessage 列表序列化为 [{role, content}] 格式，用于持久化

    LangChain 内部类型 → API 格式映射：
      BaseMessage.type   → 序列化 role
      "human"            → "user"
      "ai"               → "assistant"
      "system"           → "system"
      其他               → 原样（跳过 tool 消息——前端不需要）
    """
    LC_TYPE_TO_API = {
        "human": C.ROLE_USER,
        "ai": C.ROLE_ASSISTANT,
        "system": C.ROLE_SYSTEM,
    }

    result: list[dict] = []
    for m in msgs:
        lc_type = getattr(m, "type", "unknown")
        content = getattr(m, "content", "")
        api_role = LC_TYPE_TO_API.get(lc_type)
        if api_role:
            result.append({"role": api_role, "content": content})
    return result


def _deserialize_messages(data: list[dict]) -> list[BaseMessage]:
    """将 [{role, content}] 列表反序列化为 BaseMessage 列表"""
    result: list[BaseMessage] = []
    for m in data:
        role = m.get(C.FIELD_ROLE, "")
        content = m.get(C.FIELD_CONTENT, "")
        if role == C.ROLE_USER:
            result.append(HumanMessage(content=content))
        elif role == C.ROLE_ASSISTANT:
            result.append(AIMessage(content=content))
        elif role == C.ROLE_SYSTEM:
            result.append(SystemMessage(content=content))
    return result


async def chat_stream_session(
    agent: CompiledStateGraph,
    content: str,
    thread_id: str,
    approval: dict | None = None,
) -> AsyncIterator[dict]:
    """多轮会话隔离版流式接口——MemorySaver 主存 + SQLite 持久化备份 + 人工审批

    跨会话记忆策略（MemorySaver 优先，SQLite 冷启动恢复）：
      ┌─ 同会话续轮（MemorySaver 有状态）
      │    仅传本轮用户消息，MemorySaver 通过 add_messages 自动合并
      │
      ├─ 冷启动恢复（服务器重启，MemorySaver 空，SQLite 有数据）
      │    从 SQLite 加载历史 → 构造完整初始状态 → 传给 MemorySaver
      │
      └─ 首轮对话（MemorySaver 空，SQLite 无数据）
           注入 SYSTEM_PROMPT + 本轮用户消息

    人工审批（Human-in-the-Loop）：
      当 LLM 决定调用工具时，图路由到 approve 节点，interrupt() 暂停执行。
      流结束后检测到 interrupt → 发送 tool_approval_needed 事件给前端。
      前端展示审批对话框 → 用户批准/拒绝 → 下一次请求带 approval 字段。
      approval={"approved": True}  → 执行工具
      approval={"approved": False} → 给 LLM 注入拒绝消息，让它基于已有知识回答

    Args:
        agent: build_agent() 返回的 CompiledStateGraph
        content: 用户本轮输入文本
        thread_id: 会话 ID，由前端生成 UUID 并在后续请求中复用
        approval: 可选，审批决策（批准/拒绝），用于恢复被 interrupt 暂停的图

    Yields:
        与 chat_stream() 相同的事件格式 + tool_approval_needed
    """
    config: dict = {C.CONFIG_CONFIGURABLE: {C.CONFIG_THREAD_ID: thread_id}}

    # ── Step 0: 检测是否处于 interrupt 状态（需审批恢复） ───────────────
    state_snapshot = agent.get_state(config)
    if state_snapshot.interrupts:
        # 图已暂停等待审批
        if approval is None:
            logger.error("interrupt 状态但未提供审批决策 | thread=%s", thread_id)
            yield {C.FIELD_TYPE: C.EVENT_ERROR, C.FIELD_MESSAGE: C.ERROR_APPROVAL_REQUIRED}
            return

        # 校验 approval 格式（必须是 dict）
        if not isinstance(approval, dict):
            logger.error("审批决策格式错误 | thread=%s type=%s", thread_id, type(approval).__name__)
            yield {C.FIELD_TYPE: C.EVENT_ERROR, C.FIELD_MESSAGE: C.ERROR_APPROVAL_FORMAT}
            return

        # 用 Command(resume=approval) 恢复图执行
        logger.info(C.LOG_APPROVAL_RESUMED, thread_id, "approved" if approval.get(C.FIELD_APPROVAL) else "rejected")
        stream_input = Command(resume=approval)
        input_messages: list[BaseMessage] = []  # 恢复时不传新消息
    else:
        # ── Step 1: 查 MemorySaver（运行时状态） ─────────────────────────
        existing_messages = state_snapshot.values.get(C.STATE_MESSAGES, [])

        if existing_messages:
            logger.info(C.LOG_SESSION_CONTINUE, thread_id, len(existing_messages))
            input_messages = [HumanMessage(content=content)]

        else:
            # ── Step 2: MemorySaver 空 → 查 SQLite（冷启动恢复） ──────────
            persisted = P.load_thread(thread_id)
            if persisted is None:
                logger.info(C.LOG_SESSION_FIRST_TURN, thread_id)
                input_messages = [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=content),
                ]
            else:
                logger.info(C.LOG_SESSION_COLD_RECOVER, thread_id, len(persisted))
                input_messages = _deserialize_messages(persisted)
                input_messages.append(HumanMessage(content=content))

        stream_input = {C.STATE_MESSAGES: input_messages}

    # ── Step 3: 统一的流式处理 ──────────────────────────────────────────────
    wiki_path_source: list[str] = []

    try:
        async for event in agent.astream_events(
            stream_input,
            config,
            version=C.ASTREAM_EVENTS_VERSION,
        ):
            kind, name, data = _extract_event(event)

            if kind == C.KIND_CHAT_MODEL_STREAM:
                token = _emit_token(data.get(C.FIELD_CHUNK))
                if token:
                    yield token

            elif kind == C.KIND_TOOL_START:
                yield {
                    C.FIELD_TYPE: C.EVENT_TOOL_START,
                    C.FIELD_TOOL: name,
                    C.FIELD_INPUT: data.get(C.FIELD_INPUT, {}),
                }

            elif kind == C.KIND_TOOL_END:
                output = data.get(C.FIELD_OUTPUT, "")
                output_str = str(output) if output else ""
                yield {
                    C.FIELD_TYPE: C.EVENT_TOOL_END,
                    C.FIELD_TOOL: name,
                    C.FIELD_OUTPUT: output_str[:C.TOOL_OUTPUT_DISPLAY_CHARS],
                }
                if output_str:
                    matched = re.findall(C.WIKI_PATH_REGEX, output_str)
                    wiki_path_source.extend(matched)

    except Exception as e:
        logger.error(C.LOG_SESSION_FAILED, thread_id, e)
        yield {C.FIELD_TYPE: C.EVENT_ERROR, C.FIELD_MESSAGE: C.ERROR_AGENT_FAILED.format(e)}
        return

    # ── Step 4: 检查新 interrupt（审批等待） ──────────────────────────────
    new_state = agent.get_state(config)
    if new_state.interrupts:
        interrupt_value = new_state.interrupts[0].value
        tool_calls_info = interrupt_value.get(C.FIELD_TOOL_CALLS, [])
        logger.info(C.LOG_APPROVAL_NEEDED, thread_id, [t.get("name") for t in tool_calls_info])
        yield {
            C.FIELD_TYPE: C.EVENT_TOOL_APPROVAL_NEEDED,
            C.FIELD_TOOL_CALLS: tool_calls_info,
        }
        return  # 不持久化，不 yield done

    # ── Step 5: 结构化提取最终回答 ───────────────────────────────────────────
    structured: AgentResponse | None = None
    final_state = agent.get_state(config)
    final_messages = final_state.values.get(C.STATE_MESSAGES, [])
    for m in reversed(final_messages):
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            structured = format_response(str(m.content))
            break

    # ── Step 6: 持久化到 SQLite ─────────────────────────────────────────────
    serialized = _serialize_messages(final_messages)
    P.save_thread(thread_id, serialized)
    logger.info("会话已持久化 | thread=%s messages=%d", thread_id, len(serialized))

    done_event: dict = {
        C.FIELD_TYPE: C.EVENT_DONE,
        C.FIELD_SOURCES: list(dict.fromkeys(wiki_path_source)),
    }
    if structured:
        done_event[C.FIELD_CITED_PAGES] = structured.cited_pages
        done_event[C.FIELD_FOLLOW_UP_QUESTIONS] = structured.follow_up_questions
    yield done_event
