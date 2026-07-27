"""
路由: Chat Agent — SSE 流式对话端点

接口:
  GET  /v1/agent/threads         — 列出所有持久化会话
  POST /v1/agent/chat            — 无状态版（前端管理全量消息）
  POST /v1/agent/chat/session    — 多轮会话隔离版（后端持久化管理历史）
"""
import json
import logging

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent import persistence as P
from src.agent.agent import build_agent, chat_stream, chat_stream_session

logger = logging.getLogger("api.routes.chat")
router = APIRouter(tags=["agent"])

# Agent 单例（懒初始化）
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


class ChatRequest(BaseModel):
    """聊天请求"""
    messages: list[dict] = Field(
        description="对话历史，[{\"role\": \"user\", \"content\": \"...\"}, ...]",
    )


class ChatSessionRequest(BaseModel):
    """多轮会话聊天请求"""
    content: str = Field(description="用户本轮输入文本")
    thread_id: str = Field(
        description="会话 ID，由前端生成 UUID 并在后续请求中复用",
        examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
    )


@router.get("/v1/agent/threads")
async def list_threads(
    limit: int = Query(20, description="最多返回条数"),
    offset: int = Query(0, description="偏移量"),
):
    """列出所有持久化的会话

    返回按最后更新时间倒序的会话列表，包含 thread_id / title / 消息数。
    """
    return {"threads": P.list_threads(limit=limit, offset=offset)}


@router.post("/v1/agent/chat/session")
async def agent_chat_session(body: ChatSessionRequest):
    """多轮会话隔离版对话 — SSE 流式返回

    每个 thread_id 有独立的状态空间：
      - 首轮：自动注入 SYSTEM_PROMPT
      - 续轮：Checkpointer 回溯历史，无需前端拼接全量消息

    前端自行生成 thread_id（如 crypto.randomUUID()）并复用。
    """
    agent = _get_agent()

    async def event_stream():
        try:
            async for event in chat_stream_session(agent, body.content, body.thread_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("SSE 流异常 | thread=%s error=%s", body.thread_id, e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/v1/agent/chat")
async def agent_chat(body: ChatRequest):
    """Agent 对话 — SSE 流式返回

    前端用 EventSource 或 fetch + ReadableStream 读取。
    事件格式：
      event: message
      data: {"type": "token", "content": "..."}

      event: message
      data: {"type": "tool_start", "tool": "...", "input": {...}}

      event: message
      data: {"type": "done", "sources": [...]}
    """
    agent = _get_agent()

    async def event_stream():
        try:
            async for event in chat_stream(agent, body.messages):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error("SSE 流异常 | error=%s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )
