"""
路由: Chat Agent — SSE 流式对话端点

接口:
  GET  /v1/agent/tools              — 列出已注册工具
  GET  /v1/agent/models             — 列出可用模型
  GET  /v1/agent/threads            — 列出所有持久化会话
  GET  /v1/agent/threads/{id}       — 获取单个会话详情
  PATCH /v1/agent/threads/{id}      — 重命名会话
  DELETE /v1/agent/threads/{id}     — 删除会话
  POST /v1/agent/threads/{id}/clear — 清空会话消息
  POST /v1/agent/threads/{id}/regenerate — 重新生成（SSE 流）
  POST /v1/agent/threads/{id}/feedback  — 提交反馈
  POST /v1/agent/chat               — 无状态版
  POST /v1/agent/chat/session       — 多轮会话隔离版（SSE 流）
"""
import json
import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from src.agent import build_agent, chat_stream, chat_stream_session
from src.agent import constants as C
from src.agent.action.registry import get_tool_info
from src.agent.action.response import AgentResponse, enrich_cited_pages, format_response
from src.agent.action.stream import emit_token
from src.agent.memory import store as P
from src.agent.perception.handler import deserialize_messages, extract_event, extract_sources, serialize_messages

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
    if not P.delete_thread(thread_id):
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return {"status": "ok", "thread_id": thread_id}


# ── Models 列表 ──────────────────────────────────────────────────────────────


@router.get("/v1/agent/models")
async def list_models():
    """列出所有可用的 LLM 模型

    返回已知模型注册表中的模型列表，标记当前激活的模型和已配置的模型。
    """
    current_provider = os.environ.get("LLM_PROVIDER", "deepseek")
    current_model = os.environ.get("DEEPSEEK_MODEL", C.DEFAULT_MODEL)

    # 判断哪些 provider 已配置 API Key
    has_deepseek = bool(os.environ.get(C.ENV_DEEPSEEK_API_KEY))
    has_doubao = bool(os.environ.get("ARK_API_KEY"))

    models_out = []
    for model_id, info in C.MODEL_REGISTRY.items():
        prov = info["provider"]
        configured = (prov == "deepseek" and has_deepseek) or (prov == "doubao" and has_doubao)
        is_active = (prov == current_provider and model_id == current_model)
        models_out.append({
            C.FIELD_MODEL_ID: model_id,
            C.FIELD_DISPLAY_NAME: info["display_name"],
            "provider": prov,
            C.FIELD_CAPABILITIES: info["capabilities"],
            C.FIELD_IS_ACTIVE: is_active,
            C.FIELD_CONFIGURED: configured,
        })

    logger.info(C.LOG_MODELS_LISTED, current_model, len(models_out))
    return {
        "status": "ok",
        C.FIELD_CURRENT: {
            C.FIELD_MODEL_ID: current_model,
            "provider": current_provider,
        },
        C.FIELD_MODELS: models_out,
    }


# ── 清空对话 ────────────────────────────────────────────────────────────────


class ClearResponse(BaseModel):
    """清空会话响应"""
    status: str = "ok"
    thread_id: str
    action: str = "cleared"
    messages_removed: int = 0


@router.post("/v1/agent/threads/{thread_id}/clear")
async def clear_thread(thread_id: str):
    """清空会话消息，保留线程本身（thread_id、标题、元数据）"""
    removed = P.clear_thread(thread_id)
    return ClearResponse(thread_id=thread_id, messages_removed=removed)


# ── 重新生成 ────────────────────────────────────────────────────────────────


@router.post("/v1/agent/threads/{thread_id}/regenerate")
async def regenerate_thread(thread_id: str):
    """重新生成上一条助手回复 — SSE 流式返回

    后端加载线程，删除最后一条助手回复，
    用相同的用户输入重新调用 Agent，流式返回新回复。
    """
    agent = _get_agent()

    async def event_stream():
        try:
            # 1. 加载 thread
            loaded = P.load_thread(thread_id)
            if loaded is None:
                yield f"data: {json.dumps({'type': 'error', 'message': C.ERROR_THREAD_NOT_FOUND}, ensure_ascii=False)}\n\n"
                return
            msgs, sinks, wm = loaded

            # 2. 反序列化，找到最后一条 HumanMessage
            deserialized = deserialize_messages(msgs)
            trim_index = len(deserialized)
            last_user_content = None
            for i in range(len(deserialized) - 1, -1, -1):
                if isinstance(deserialized[i], HumanMessage):
                    last_user_content = str(deserialized[i].content)
                    trim_index = i + 1
                    break

            if last_user_content is None:
                yield f"data: {json.dumps({'type': 'error', 'message': C.ERROR_NO_USER_MESSAGE}, ensure_ascii=False)}\n\n"
                return

            trimmed = deserialized[:trim_index]

            # 3. 持久化修剪后的状态到 SQLite
            trimmed_serialized = serialize_messages(trimmed)
            P.save_thread(thread_id, trimmed_serialized, attention_sinks=sinks, working_memory=wm)

            # 4. 直接运行 agent（使用独立 config 避免 MemorySaver 冲突）
            stream_input: dict = {C.STATE_MESSAGES: trimmed}
            if sinks:
                stream_input[C.STATE_ATTENTION_SINKS] = sinks
            if wm:
                stream_input[C.STATE_WORKING_MEMORY] = wm
            regen_config: dict = {
                C.CONFIG_CONFIGURABLE: {
                    C.CONFIG_THREAD_ID: f"{thread_id}_reg",
                }
            }

            wiki_path_source: list[str] = []
            async for event in agent.astream_events(stream_input, regen_config, version=C.ASTREAM_EVENTS_VERSION):
                kind, name, data = extract_event(event)

                if kind == C.KIND_CHAT_MODEL_STREAM:
                    token = emit_token(data.get(C.FIELD_CHUNK))
                    if token:
                        yield f"data: {json.dumps(token, ensure_ascii=False)}\n\n"

                elif kind == C.KIND_TOOL_START:
                    yield f"data: {json.dumps({
                        C.FIELD_TYPE: C.EVENT_TOOL_START,
                        C.FIELD_TOOL: name,
                        C.FIELD_INPUT: data.get(C.FIELD_INPUT, {}),
                    }, ensure_ascii=False)}\n\n"

                elif kind == C.KIND_TOOL_END:
                    output = str(data.get(C.FIELD_OUTPUT, "")) or ""
                    yield f"data: {json.dumps({
                        C.FIELD_TYPE: C.EVENT_TOOL_END,
                        C.FIELD_TOOL: name,
                        C.FIELD_OUTPUT: output[:C.TOOL_OUTPUT_DISPLAY_CHARS],
                    }, ensure_ascii=False)}\n\n"
                    if output:
                        wiki_path_source.extend(extract_sources(output))

            # 5. 结构化提取最终回答
            structured: AgentResponse | None = None
            try:
                final_state = agent.get_state(regen_config)
                final_messages = final_state.values.get(C.STATE_MESSAGES, [])
                for m in reversed(final_messages):
                    if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
                        structured = await asyncio.to_thread(format_response, str(m.content))
                        break
            except Exception:
                pass

            # 6. 持久化到 SQLite
            final_state = agent.get_state(regen_config)
            new_serialized = serialize_messages(final_state.values.get(C.STATE_MESSAGES, []))
            final_sinks = final_state.values.get(C.STATE_ATTENTION_SINKS, sinks)
            final_wm = final_state.values.get(C.STATE_WORKING_MEMORY, wm)
            P.save_thread(thread_id, new_serialized, attention_sinks=final_sinks, working_memory=final_wm)

            # 7. 构建 done 事件（含 cited_pages 富化）
            done_event: dict = {
                C.FIELD_TYPE: C.EVENT_DONE,
                C.FIELD_SOURCES: list(dict.fromkeys(wiki_path_source)),
            }
            if structured:
                done_event[C.FIELD_CITED_PAGES] = enrich_cited_pages(structured.cited_pages)
                done_event[C.FIELD_FOLLOW_UP_QUESTIONS] = structured.follow_up_questions
            yield f"data: {json.dumps(done_event, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(C.LOG_REGENERATE_ERROR, thread_id, e)
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


# ── 反馈 ─────────────────────────────────────────────────────────────────────


class FeedbackRequest(BaseModel):
    """反馈请求"""
    message_index: int = Field(description="消息在 thread 中的序号（0-based）", ge=0)
    rating: str = Field(description="反馈类型：positive 或 negative", pattern=r"^(positive|negative)$")
    comment: str = Field(default="", description="可选文字反馈", max_length=500)


class FeedbackResponse(BaseModel):
    """反馈存储响应"""
    status: str = "ok"
    thread_id: str
    recorded: bool


@router.post("/v1/agent/threads/{thread_id}/feedback")
async def submit_feedback(thread_id: str, body: FeedbackRequest):
    """提交对某条助手消息的反馈（点赞/点踩 + 可选文字）"""
    recorded = P.store_feedback(thread_id, body.message_index, body.rating, body.comment)
    if not recorded:
        exist = P.load_thread(thread_id)
        if exist is None:
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
        total = len(exist[0])
        raise HTTPException(
            status_code=400,
            detail=f"message_index {body.message_index} out of range [0, {total})",
        )
    return FeedbackResponse(thread_id=thread_id, recorded=True)


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
