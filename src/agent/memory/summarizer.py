"""
对话摘要压缩模块 — 将早期对话历史压缩为 LLM 生成的摘要

核心函数:
  condense_history(messages, llm) -> list[BaseMessage]
    当消息数超过阈值时，调用 LLM 将早期对话压缩为一条摘要 SystemMessage，
    通过 RemoveMessage 移除旧消息并用摘要替换。

使用结构化输出（with_structured_output）确保摘要格式一致性。

与 AgentState 的集成:
  summarizer 节点在 call_model 之后、图结束之前运行。
  当非 SystemMessage 数量超过 SUMMARIZE_THRESHOLD 时触发。

使用方法:
  from src.agent.memory.summarizer import condense_history
  compressed = condense_history(state["messages"], llm)
"""

import logging
from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel, Field

from src.agent import constants as C

if TYPE_CHECKING:
    from langchain_core.messages import RemoveMessage

logger = logging.getLogger("agent.summarizer")


# ── 结构化输出模型 ─────────────────────────────────────────────────────────


class SummaryResult(BaseModel):
    """LLM 生成的对话摘要结构化输出

    使用 with_structured_output 保证输出格式一致，
    替代原有的裸文本 + prompt 软约束方式。
    """
    summary: str = Field(description="对话摘要，300字以内，保留核心问题和知识点")
    key_topics: list[str] = Field(description="涉及的核心话题列表", default=[])


logger = logging.getLogger("agent.summarizer")


# ── 判断 ─────────────────────────────────────────────────────────────────────


def should_summarize(messages: list[BaseMessage]) -> bool:
    """检查是否需要触发摘要压缩

    条件：非 SystemMessage 数量超过 SUMMARIZE_THRESHOLD

    Args:
        messages: 当前状态的全部消息

    Returns:
        True 表示需要压缩
    """
    non_system = [m for m in messages if not isinstance(m, SystemMessage)]
    return len(non_system) > C.SUMMARIZE_THRESHOLD


# ── 格式化 ────────────────────────────────────────────────────────────────────


def _format_conversation(messages: list[BaseMessage], existing_summary: str | None = None) -> str:
    """将消息列表格式化为 LLM 友好的文本

    Args:
        messages: 需要压缩的对话消息
        existing_summary: 已有摘要文本（如有则合并）

    Returns:
        格式化后的对话文本字符串
    """
    parts: list[str] = []
    if existing_summary:
        parts.append(f"[已有摘要]\n{existing_summary}\n")

    parts.append("[最新对话]")
    for m in messages:
        role_label = {
            "human": "用户",
            "ai": "助手",
            "tool": "工具",
        }.get(getattr(m, "type", ""), "系统")
        content = getattr(m, "content", "")
        # ToolMessage 内容可能较长，截断显示
        if getattr(m, "type", "") == "tool":
            content = content[:200] + ("..." if len(content) > 200 else "")
        parts.append(f"{role_label}: {content}")

    return "\n\n".join(parts)


# ── 摘要生成 ──────────────────────────────────────────────────────────────────


def _call_summarize_llm(text: str, llm: "BaseChatModel") -> SummaryResult:
    """调用 LLM 生成对话摘要（结构化输出）

    使用 with_structured_output 替代原始文本解析，
    LLM 输出受 Pydantic 模型约束，字段格式由 API 保证而非 prompt 软约束。

    Args:
        text: _format_conversation 生成的格式化对话文本
        llm: LLM 实例（不带工具绑定）

    Returns:
        SummaryResult 对象（summary + key_topics）

    Raises:
        ValueError: LLM 返回空摘要
    """
    from langchain_core.messages import HumanMessage, SystemMessage as SysMsg

    structured_llm = llm.with_structured_output(SummaryResult)
    result = structured_llm.invoke([
        SysMsg(content=C.SUMMARIZE_SYSTEM_PROMPT),
        HumanMessage(content=text),
    ])
    if not result.summary.strip():
        raise ValueError("对话摘要 LLM 返回空内容")
    logger.info("摘要结构化输出 | topics=%s", result.key_topics)
    return result


# ── 提取已有摘要 ──────────────────────────────────────────────────────────────


def _extract_existing_summary(messages: list[BaseMessage]) -> tuple[str | None, list[BaseMessage]]:
    """从消息列表中提取已有的摘要消息

    Args:
        messages: 全部消息

    Returns:
        (摘要文本, 移除摘要后的消息列表)
    """
    summary_text: str | None = None
    remaining: list[BaseMessage] = []
    for m in messages:
        if isinstance(m, SystemMessage) and m.content.startswith(C.SUMMARIZE_PREFIX):
            summary_text = m.content[len(C.SUMMARIZE_PREFIX):]
        else:
            remaining.append(m)
    return summary_text, remaining


# ── 主入口 ────────────────────────────────────────────────────────────────────


def condense_history(
    messages: list[BaseMessage],
    llm: "BaseChatModel",
    sink_context: str = "",
) -> tuple[list["RemoveMessage"], "SystemMessage | None"]:
    """将早期对话历史压缩为摘要

    当非 SystemMessage 数量超过阈值时:
      1. 提取已有摘要（如有）
      2. 将最早的若干轮对话格式化为文本
      3. 调用 LLM 生成新摘要
      4. 返回 RemoveMessage 列表（移除旧消息）和新摘要 SystemMessage

    Args:
        messages: 当前状态的全部消息
        llm: LLM 实例（不绑定工具的 plain 实例）
        sink_context: Attention Sink 提取的关键信息文本，注入摘要 prompt
          让 LLM 在生成摘要时保留这些被锚定的内容

    Returns:
        (remove_ops, summary_msg)
        - remove_ops: 用于移除旧消息的 RemoveMessage 列表
        - summary_msg: 新摘要 SystemMessage，无需压缩时为 None
    """
    # 延迟导入，避免循环依赖
    from langchain_core.messages import RemoveMessage

    if not should_summarize(messages):
        logger.info(C.LOG_SUMMARIZE_SKIP, len(messages), C.SUMMARIZE_THRESHOLD)
        return [], None

    logger.info(C.LOG_SUMMARIZE_START, len(messages),
                sum(1 for m in messages if isinstance(m, SystemMessage)),
                sum(1 for m in messages if not isinstance(m, SystemMessage)))

    # 1. 提取已有摘要
    existing_summary, msg_without_summary = _extract_existing_summary(messages)

    # 2. 分离 system 和 conversation 消息
    system_msgs = [m for m in msg_without_summary if isinstance(m, SystemMessage)]
    conversation = [m for m in msg_without_summary if not isinstance(m, SystemMessage)]

    # 3. 决定保留最新的多少条
    keep_count = C.SUMMARIZE_KEEP_LATEST_TURNS * 2  # 1 轮 = user + assistant
    if len(conversation) <= keep_count:
        logger.info(C.LOG_SUMMARIZE_SKIP, len(messages), "(conversation <= keep)")
        return [], None

    # 4. 分离需要压缩的部分
    to_compress = conversation[:-keep_count]
    to_keep = conversation[-keep_count:]

    # 5. 过滤掉 ToolMessage（内部细节，不需要编入摘要）
    compress_text = [m for m in to_compress if getattr(m, "type", "") != "tool"]

    # 6. 调用 LLM 生成摘要（结构化输出），注入 sink_context
    try:
        formatted = _format_conversation(compress_text, existing_summary)
        # 如果有 sink context，追加到格式化文本末尾
        if sink_context:
            formatted += f"\n\n[已锚定的关键信息（需在摘要中保留）]\n{sink_context}"
        result = _call_summarize_llm(formatted, llm)
        summary_text = result.summary
        summary_topics = result.key_topics
    except Exception as e:
        logger.error(C.LOG_SUMMARIZE_FAILED, e)
        return [], None  # 失败时降级为不压缩

    # 7. 构建 RemoveMessage 操作（移除被压缩的旧消息）
    remove_ops: list[RemoveMessage] = []
    for m in to_compress:
        msg_id = getattr(m, "id", None)
        if msg_id:
            remove_ops.append(RemoveMessage(id=msg_id))

    # 8. 新摘要 SystemMessage（包含摘要文本 + 话题标签）
    topics_tag = f"\n\n话题: {'、'.join(summary_topics)}" if summary_topics else ""
    summary_msg = SystemMessage(content=f"{C.SUMMARIZE_PREFIX}{summary_text}{topics_tag}")

    logger.info(C.LOG_SUMMARIZE_DONE, len(to_compress), C.SUMMARIZE_KEEP_LATEST_TURNS,
                len(system_msgs) + 1 + len(to_keep))
    return remove_ops, summary_msg
