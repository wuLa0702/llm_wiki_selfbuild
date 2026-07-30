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

from src.agent import build_agent, chat_stream, chat_stream_session
from src.agent.action.registry import get_tool_info
from src.agent.memory import store as P

logger = logging.getLogger("api.routes.chat")
router = APIRouter(tags=["agent"])

# Agent 单例（懒初始化）
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


@router.get("/v1/agent/tools")
async def list_tools():
    """列出 Agent 所有已注册工具的元数据

    返回每个工具的名称、描述、参数 schema，
    供前端展示工具面板或调试使用。
    """
    return {
        "status": "ok",
        "tools": get_tool_info(),
    }


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
    approval: dict | None = Field(
        default=None,
        description="审批决策（human-in-the-loop），如 {\"approved\": true}",
    )


class ThreadRenameRequest(BaseModel):
    """会话重命名请求"""
    title: str = Field(description="新标题", min_length=1, max_length=50)


@router.get("/v1/agent/threads")
async def list_threads(
    limit: int = Query(20, description="最多返回条数"),
    offset: int = Query(0, description="偏移量"),
):
    """列出所有持久化的会话

    返回按最后更新时间倒序的会话列表，包含 thread_id / title / 消息数。
    """
    return {"threads": P.list_threads(limit=limit, offset=offset)}


@router.get("/v1/agent/threads/{thread_id}")
async def get_thread(thread_id: str):
    """获取单个会话详情 — 含完整消息历史"""
    loaded = P.load_thread(thread_id)
    if loaded is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    messages, attention_sinks, working_memory = loaded
    row = P._get_conn().execute(
        "SELECT title, created_at, updated_at FROM agent_threads WHERE thread_id = ?",
        (thread_id,),
    ).fetchone()
    return {
        "thread_id": thread_id,
        "title": row["title"] if row else "",
        "created_at": row["created_at"] if row else 0,
        "updated_at": row["updated_at"] if row else 0,
        "messages": messages,
        "attention_sinks": attention_sinks,
        "working_memory": working_memory,
    }


@router.patch("/v1/agent/threads/{thread_id}")
async def rename_thread(thread_id: str, body: ThreadRenameRequest):
    """重命名会话标题"""
    from fastapi import HTTPException
    if not P.rename_thread(thread_id, body.title):
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return {"status": "ok", "thread_id": thread_id, "title": body.title.strip()[:50]}


@router.delete("/v1/agent/threads/{thread_id}")
async def delete_thread(thread_id: str):
    """删除会话及其全部消息、索引数据"""
    from fastapi import HTTPException
    if not P.delete_thread(thread_id):
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return {"status": "ok", "thread_id": thread_id}


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
            async for event in chat_stream_session(agent, body.content, body.thread_id, approval=body.approval):
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
