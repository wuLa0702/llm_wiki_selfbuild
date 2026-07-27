"""
Agent 持久化层 — 基于 SQLite 的对话记忆存储

职责：
  - 将多轮对话消息持久化到 SQLite 数据库
  - 支持按 thread_id 保存/加载/列举
  - 作为 AsyncSqliteSaver 的替代方案（Python 3.14 兼容）
  - 重启后消息不丢失

与 LangGraph Checkpointer 的关系：
  运行时仍使用 MemorySaver（图状态），
  此层在应用层负责保存/恢复对话消息列表。
  启动时从 SQLite 加载历史 → 喂给 chat_stream_session。
"""

import json
import logging
import os
import sqlite3
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from src.agent import constants as C

logger = logging.getLogger("agent.persistence")

# 数据库连接（模块级单例，check_same_thread=False 支持跨线程访问）
_conn: sqlite3.Connection | None = None
_ENSURED = False


def _get_conn() -> sqlite3.Connection:
    """获取 SQLite 连接（懒初始化）"""
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(C.PERSISTENCE_DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn


def _ensure_table():
    """确保 threads 表存在（幂等）"""
    global _ENSURED
    if _ENSURED:
        return
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS agent_threads (
            thread_id   TEXT PRIMARY KEY,
            messages    TEXT NOT NULL,       -- JSON 序列化的消息列表
            created_at  REAL NOT NULL,       -- 创建时间戳
            updated_at  REAL NOT NULL,       -- 最后更新时间戳
            title       TEXT DEFAULT ''      -- 会话标题（自动提取）
        )
    """)
    conn.commit()
    _ENSURED = True


# ── 对外接口 ──────────────────────────────────────────────────────────────────


def save_thread(thread_id: str, messages: list[dict]) -> None:
    """保存（覆盖）指定 thread 的消息列表

    Args:
        thread_id: 会话唯一标识
        messages: [{role, content}, ...] 格式的消息列表
    """
    _ensure_table()
    now = time.time()
    # 首条消息自动作为标题
    title = messages[0].get("content", "")[:50] if messages else ""

    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO agent_threads (thread_id, messages, created_at, updated_at, title)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(thread_id) DO UPDATE SET
            messages = excluded.messages,
            updated_at = excluded.updated_at,
            title = CASE WHEN excluded.title != '' THEN excluded.title ELSE title END
        """,
        (thread_id, json.dumps(messages, ensure_ascii=False), now, now, title),
    )
    conn.commit()


def load_thread(thread_id: str) -> list[dict] | None:
    """加载指定 thread 的消息历史

    Returns:
        [{role, content}, ...] 或 None（thread 不存在）
    """
    _ensure_table()
    row = _get_conn().execute(
        "SELECT messages FROM agent_threads WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    if row is None:
        return None
    return json.loads(row["messages"])


def list_threads(limit: int = 20, offset: int = 0) -> list[dict[str, Any]]:
    """列出所有持久化的会话

    Returns:
        [{thread_id, title, message_count, created_at, updated_at}, ...]
    """
    _ensure_table()
    rows = _get_conn().execute(
        """
        SELECT thread_id, title, created_at, updated_at,
               json_array_length(messages) as message_count
        FROM agent_threads
        ORDER BY updated_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_thread(thread_id: str) -> bool:
    """删除指定 thread 及消息历史

    Returns:
        True（存在并删除）/ False（不存在）
    """
    _ensure_table()
    cur = _get_conn().execute(
        "DELETE FROM agent_threads WHERE thread_id = ?", (thread_id,)
    )
    _get_conn().commit()
    return cur.rowcount > 0


def thread_exists(thread_id: str) -> bool:
    """检查 thread 是否存在"""
    _ensure_table()
    row = _get_conn().execute(
        "SELECT 1 FROM agent_threads WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    return row is not None


def migrate_memorysaver_to_sqlite():
    """冷启动辅助：若 MemorySaver 在内存中有未持久化的对话，
    插件式迁移入口（当前无数据需迁移，留作接口）
    """
    _ensure_table()
    logger.info("持久化存储就绪 | db=%s", C.PERSISTENCE_DB_PATH)
