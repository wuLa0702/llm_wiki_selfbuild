"""
Agent 会话编排层 — 多轮会话隔离 + 流式接口

职责（协调 4 大模块）：
  - 感知：消息反序列化、来源提取、输入窗口截断
  - 规划：调用 build_agent() 获取编译后的图
  - 记忆：SQLite 持久化 + MemorySaver 检查
  - 执行：流式事件处理、响应格式化

chat_stream_session 是本层的核心入口，
它协调 4 个模块完成"接收输入 → 处理 → 持久化 → 输出"的完整链路。
"""

import json
import logging
import re
from collections.abc import AsyncIterator

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from src.agent import constants as C
from src.agent.action.response import AgentResponse, format_response
from src.agent.action.stream import emit_token
from src.agent.memory import store as M
from src.agent.perception.handler import deserialize_messages, extract_event, extract_sources, serialize_messages
from src.agent.planning.graph import app, summarizer_llm  # noqa: F401 — also used by _archive_stale_thread
from src.agent.planning.prompt import SYSTEM_PROMPT

logger = logging.getLogger("agent.session")


# ── 记忆降级归档 ──────────────────────────────────────────────────────────────


def _archive_stale_thread(thread_id: str) -> None:
    """懒归档检查：如果 thread 够旧且未归档，将消息压缩为摘要

    执行条件：
      - thread 存在且未归档
      - 消息数 ≥ 3（至少有意义的对话）
      - 闲置天数 ≥ ARCHIVE_DAYS

    归档说明：原始对话完整保留在 SQLite 中（messages 列不变），
    仅向 archive_summary 列写入摘要文本，供恢复时注入 LLM 上下文。
    归档失败不阻断主流程（catch 所有异常）。
    """
    # 已归档？跳过
    if M.is_thread_archived(thread_id):
        logger.info(C.LOG_ARCHIVE_SKIP, thread_id, "已归档")
        return

    # 加载数据
    loaded = M.load_thread(thread_id)
    if loaded is None:
        logger.info(C.LOG_ARCHIVE_SKIP, thread_id, "thread 不存在")
        return
    messages, sinks, wm = loaded

    # 消息太少？跳过（归档无意义）
    if len(messages) < 3:
        logger.info(C.LOG_ARCHIVE_SKIP, thread_id, f"消息数={len(messages)} < 3")
        return

    # 够旧？
    age_days = M.get_thread_age_days(thread_id)
    if age_days is None or age_days < C.ARCHIVE_DAYS:
        logger.info(C.LOG_ARCHIVE_SKIP, thread_id,
                    f"最近活跃 age={age_days:.1f}d < {C.ARCHIVE_DAYS}d")
        return

    logger.info(C.LOG_ARCHIVE_START, thread_id, age_days)
    try:
        from langchain_core.messages import HumanMessage, SystemMessage as SysMsg
        from src.agent.memory.summarizer import SummaryResult

        # 格式化消息为 LLM 输入文本
        parts: list[str] = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # 截断过长内容（工具输出等）
            if len(content) > 500:
                content = content[:500] + "..."
            parts.append(f"[{role}]: {content}")

        conversation_text = "\n\n".join(parts)

        # 调用汇总 LLM 生成归档摘要
        structured_llm = summarizer_llm.with_structured_output(SummaryResult)
        result = structured_llm.invoke([
            SysMsg(content=C.ARCHIVE_SYSTEM_PROMPT),
            HumanMessage(content=f"压缩以下完整对话为精炼归档摘要：\n\n{conversation_text}"),
        ])

        if not result.summary.strip():
            logger.warning(C.LOG_ARCHIVE_ERROR, thread_id, "LLM 返回空摘要")
            return

        # 写回（仅存储摘要列，不修改原始 messages）
        M.store_archive_summary(thread_id, result.summary)
        logger.info(C.LOG_ARCHIVE_DONE, thread_id, len(messages), 1)

    except Exception as e:
        logger.warning(C.LOG_ARCHIVE_ERROR, thread_id, e)
        # 归档失败不阻断主流程



# ═══════════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════════


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
        cold_sinks: list[dict] = []
        cold_wm: dict = {}

        if existing_messages:
            logger.info(C.LOG_SESSION_CONTINUE, thread_id, len(existing_messages))
            input_messages = [HumanMessage(content=content)]

        else:
            # ── Step 2: 懒归档检查 ───────────────────────────────────────
            # MemorySaver 空 → 查 SQLite 前先检查是否需要归档
            _archive_stale_thread(thread_id)

            # ── Step 3: 查 SQLite（冷启动恢复） ──────────────────────────
            persisted = M.load_thread(thread_id)
            if persisted is None:
                logger.info(C.LOG_SESSION_FIRST_TURN, thread_id)
                input_messages = [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content=content),
                ]
            else:
                persisted_msgs, cold_sinks, cold_wm = persisted
                # 检测是否从归档恢复（原始消息完整保留，摘要注入 LLM 上下文）
                if M.is_thread_archived(thread_id):
                    summary_text = M.get_archive_summary(thread_id) or ""
                    logger.info("会话从归档恢复 | thread=%s summary_len=%d messages=%d",
                                thread_id, len(summary_text), len(persisted_msgs))
                    # 注入归档摘要提示 + 仍保留原始消息供 LLM 参考
                    notice = SystemMessage(content=C.ARCHIVE_RESTORE_NOTICE.format(summary=summary_text))
                    input_messages = deserialize_messages(persisted_msgs)
                    input_messages.insert(0, notice)
                    input_messages.append(HumanMessage(content=content))
                    # 归档恢复后 sinks 和 wm 仍然可用，但不再注入（简化处理）
                    cold_sinks = []
                    cold_wm = {}
                else:
                    logger.info(C.LOG_SESSION_COLD_RECOVER, thread_id, len(persisted_msgs))
                    input_messages = deserialize_messages(persisted_msgs)
                    input_messages.append(HumanMessage(content=content))

        stream_input: dict = {C.STATE_MESSAGES: input_messages}
        if cold_sinks:
            stream_input[C.STATE_ATTENTION_SINKS] = cold_sinks
        if cold_wm:
            stream_input[C.STATE_WORKING_MEMORY] = cold_wm

    # ── Step 3: 统一的流式处理 ──────────────────────────────────────────────
    wiki_path_source: list[str] = []

    try:
        async for event in agent.astream_events(
            stream_input,
            config,
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
                    matched = extract_sources(output_str)
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
    serialized = serialize_messages(final_messages)
    final_sinks = final_state.values.get(C.STATE_ATTENTION_SINKS, [])
    final_wm = final_state.values.get(C.STATE_WORKING_MEMORY, {})
    M.save_thread(thread_id, serialized, attention_sinks=final_sinks, working_memory=final_wm)
    logger.info("会话已持久化 | thread=%s messages=%d sinks=%d wm=%s",
                thread_id, len(serialized), len(final_sinks), list(final_wm.keys()))

    # ── Step 7: 构建索引（异步不阻塞） ──────────────────────────────────────
    try:
        M.index_thread_messages(thread_id, serialized)
        M.extract_thread_entities(thread_id, serialized)
    except Exception as e:
        logger.warning("索引构建失败（非阻断）| thread=%s error=%s", thread_id, e)

    done_event: dict = {
        C.FIELD_TYPE: C.EVENT_DONE,
        C.FIELD_SOURCES: list(dict.fromkeys(wiki_path_source)),
    }
    if structured:
        done_event[C.FIELD_CITED_PAGES] = structured.cited_pages
        done_event[C.FIELD_FOLLOW_UP_QUESTIONS] = structured.follow_up_questions
    yield done_event
