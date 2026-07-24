"""
Agent 构建 + 流式对话接口

导出接口:
  build_agent() -> CompiledStateGraph
  chat_stream(messages) -> AsyncIterator[dict]
  chat_stream_session(content, thread_id) -> AsyncIterator[dict]

接口固定，换 LLM Provider 或 LangGraph 版本时路由层和前端不改。
"""

import logging
import os
import re
from collections.abc import AsyncIterator
from typing import Annotated, Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from src.agent import constants as C
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


def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    """判断 LLM 输出是否需要执行工具——图分支路由函数"""
    last_msg = state[C.STATE_MESSAGES][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return C.NODE_TOOLS
    return "__end__"


# ── 图构建 ────────────────────────────────────────────────────────────────────

builder = StateGraph(AgentState)
builder.add_node(C.NODE_AGENT, call_model)
builder.add_node(C.NODE_TOOLS, tool_node)
builder.set_entry_point(C.NODE_AGENT)
builder.add_edge(C.NODE_TOOLS, C.NODE_AGENT)
builder.add_conditional_edges(C.NODE_AGENT, should_continue)

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

async def chat_stream_session(
    agent: CompiledStateGraph,
    content: str,
    thread_id: str,
) -> AsyncIterator[dict]:
    """多轮会话隔离版流式接口——基于 LangGraph Checkpointer 管理对话历史

    原理：
      - 每个 thread_id 有独立的状态空间，互不干扰
      - 自动检测是否首轮：首轮注入 SYSTEM_PROMPT，后续轮次 Checkpointer 已有
      - add_messages reducer 负责合并新消息到历史状态，而非覆盖
      - 前端只需传本轮 content + 唯一 thread_id（如 UUID），无需拼接全量历史

    Args:
        agent: build_agent() 返回的 CompiledStateGraph（必须含 Checkpointer）
        content: 用户本轮输入文本
        thread_id: 会话 ID，由前端生成 UUID 并在后续请求中复用

    Yields:
        与 chat_stream() 完全相同的事件格式
    """
    config: dict = {C.CONFIG_CONFIGURABLE: {C.CONFIG_THREAD_ID: thread_id}}

    # get_state() 若无持久化状态返回空状态，以此判断是否首轮
    state_snapshot = agent.get_state(config)
    existing_messages = state_snapshot.values.get(C.STATE_MESSAGES, [])
    is_first_turn = not existing_messages

    input_messages: list[BaseMessage] = []
    if is_first_turn:
        logger.info(C.LOG_SESSION_FIRST_TURN, thread_id)
        input_messages.append(SystemMessage(content=SYSTEM_PROMPT))
    else:
        logger.debug(C.LOG_SESSION_CONTINUE, thread_id, len(existing_messages))
    input_messages.append(HumanMessage(content=content))

    wiki_path_source: list[str] = []

    try:
        async for event in agent.astream_events(
            {C.STATE_MESSAGES: input_messages},
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

    yield {C.FIELD_TYPE: C.EVENT_DONE, C.FIELD_SOURCES: list(dict.fromkeys(wiki_path_source))}
