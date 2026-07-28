"""
感知模块 — 输入/输出消息处理

职责：
  - 消息格式转换（dict ↔ LangChain BaseMessage）
  - 来源页面提取（从 tool 输出中解析 wiki 路径）
  - 输入窗口截断（超出 MAX_MESSAGE_TURNS 的部分丢弃）
  - 角色映射（"human" ↔ "user", "ai" ↔ "assistant"）
"""

import logging
import re
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.agent import constants as C

logger = logging.getLogger(__name__)


# ── 消息序列化 / 反序列化 ──────────────────────────────────────────────────


def serialize_messages(msgs: list[BaseMessage]) -> list[dict[str, str]]:
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

    result: list[dict[str, str]] = []
    for m in msgs:
        lc_type = getattr(m, "type", "unknown")
        content = getattr(m, "content", "")
        api_role = LC_TYPE_TO_API.get(lc_type)
        if api_role:
            result.append({C.FIELD_ROLE: api_role, C.FIELD_CONTENT: content})
    return result


def deserialize_messages(data: list[dict[str, str]]) -> list[BaseMessage]:
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


# ── 用户输入转换 ──────────────────────────────────────────────────────────


def convert_to_lc_messages(messages: list[dict[str, str]]) -> list[BaseMessage]:
    """将前端 [{role, content}] 格式转换为 LangChain BaseMessage 列表

    Args:
        messages: [{"role": "user"|"assistant"|"system", "content": "..."}, ...]

    Returns:
        转换后的 BaseMessage 列表
    """
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
    return lc_messages


def truncate_window(messages: list[BaseMessage], max_turns: int) -> list[BaseMessage]:
    """窗口截断：保留 SystemMessage（人格设定）+ 最近 N 轮对话

    Args:
        messages: 全部消息列表
        max_turns: 最多保留的对话轮数（1 轮 = 1 user + 1 assistant）

    Returns:
        截断后的消息列表
    """
    system_msgs = [m for m in messages if isinstance(m, SystemMessage)]
    non_system = [m for m in messages if not isinstance(m, SystemMessage)]
    if len(non_system) > max_turns:
        logger.warning(C.LOG_WINDOW_EXCEEDED, len(non_system), max_turns)
        non_system = non_system[-max_turns:]
    return system_msgs + non_system


# ── 来源提取 ──────────────────────────────────────────────────────────────


def extract_sources(output_str: str) -> list[str]:
    """从工具输出文本中提取 Wiki 页面路径（`xxx.md` 格式）

    Args:
        output_str: 工具输出的文本

    Returns:
        提取到的 wiki 页面路径列表
    """
    return re.findall(C.WIKI_PATH_REGEX, output_str)


# ── 事件解构 ──────────────────────────────────────────────────────────────


def extract_event(event: dict) -> tuple[str, str, dict]:
    """解构 astream_events 事件为 (kind, name, data) 三元组"""
    return (
        event.get(C.FIELD_EVENT, ""),
        event.get(C.FIELD_NAME, ""),
        event.get(C.FIELD_DATA, {}),
    )
