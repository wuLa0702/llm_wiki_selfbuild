"""
执行模块 — 流式事件处理

职责：
  - 定义流式事件辅助函数（token 提取）
  - chat_stream 无状态流式接口（前端管理全量消息）
"""

import logging
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph.state import CompiledStateGraph

from src.agent import constants as C
from src.agent.perception.handler import convert_to_lc_messages, extract_event, extract_sources, truncate_window

logger = logging.getLogger("agent.stream")


# ── Token 提取 ──────────────────────────────────────────────────────────────


def emit_token(chunk) -> dict | None:
    """从 astream_events chunk 中提取 token 事件，无内容返回 None"""
    if chunk is None:
        return None
    content = getattr(chunk, C.FIELD_CONTENT, "")
    if not content:
        return None
    return {C.FIELD_TYPE: C.EVENT_TOKEN, C.FIELD_CONTENT: content}


# ── 无状态流式对话 ──────────────────────────────────────────────────────────


async def chat_stream(
    agent: CompiledStateGraph,
    messages: list[dict],
) -> AsyncIterator[dict]:
    """流式对话接口 —— 生产 SSE 事件（无状态版，前端管理全量消息）

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
    lc_messages = convert_to_lc_messages(messages)

    if not lc_messages:
        yield {C.FIELD_TYPE: C.EVENT_ERROR, C.FIELD_MESSAGE: C.ERROR_EMPTY_MESSAGES}
        return

    # 窗口截断
    lc_messages = truncate_window(lc_messages, C.MAX_MESSAGE_TURNS)

    wiki_path_source: list[str] = []

    try:
        async for event in agent.astream_events(
            {C.STATE_MESSAGES: lc_messages},
            version=C.ASTREAM_EVENTS_VERSION,
        ):
            kind, name, data = extract_event(event)

            if kind == C.KIND_CHAT_MODEL_STREAM:
                token = emit_token(data.get(C.FIELD_CHUNK))
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
                    wiki_path_source.extend(extract_sources(output_str))

    except Exception as e:
        logger.error(C.LOG_STREAM_FAILED, e)
        yield {C.FIELD_TYPE: C.EVENT_ERROR, C.FIELD_MESSAGE: C.ERROR_AGENT_FAILED.format(e)}
        return

    yield {C.FIELD_TYPE: C.EVENT_DONE, C.FIELD_SOURCES: list(dict.fromkeys(wiki_path_source))}
