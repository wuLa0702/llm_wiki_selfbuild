"""
路由: Chat Agent — POST /v1/agent/chat

SSE 流式对话端点，对接 LangChain Agent。
"""
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.agent.agent import build_agent, chat_stream

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


class ChatMessage(BaseModel):
    """单条消息"""
    role: str = Field(description="user / assistant / system")
    content: str = Field(description="消息内容")


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
