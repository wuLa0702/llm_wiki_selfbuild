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
import re
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
            thread_id       TEXT PRIMARY KEY,
            messages        TEXT NOT NULL,       -- JSON 序列化的消息列表
            attention_sinks TEXT DEFAULT '[]',   -- JSON 序列化的 Attention Sink 列表
            working_memory  TEXT DEFAULT '{}',   -- JSON 序列化的工作记忆字典
            created_at      REAL NOT NULL,       -- 创建时间戳
            updated_at      REAL NOT NULL,       -- 最后更新时间戳
            title           TEXT DEFAULT ''      -- 会话标题（自动提取）
        )
    """)
    conn.commit()
    # 幂等迁移：旧表可能缺少 attention_sinks、working_memory 或 archive_summary 列
    _migrate_add_column(conn, "attention_sinks", "TEXT", "'[]'")
    _migrate_add_column(conn, "working_memory", "TEXT", "'{}'")
    _migrate_add_column(conn, "archive_summary", "TEXT", "NULL")
    _ENSURED = True


def _migrate_add_column(conn: sqlite3.Connection, col_name: str, col_type: str, default: str):
    """安全迁移：为旧表添加缺失的列（幂等）"""
    try:
        conn.execute(f"ALTER TABLE agent_threads ADD COLUMN {col_name} {col_type} DEFAULT {default}")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 列已存在，忽略


# ── 对外接口 ──────────────────────────────────────────────────────────────────


def save_thread(thread_id: str, messages: list[dict], attention_sinks: list[dict] | None = None, working_memory: dict | None = None) -> None:
    """保存（覆盖）指定 thread 的消息列表、Attention Sink 和工作记忆

    Args:
        thread_id: 会话唯一标识
        messages: [{role, content}, ...] 格式的消息列表
        attention_sinks: 可选，Attention Sink 列表
        working_memory: 可选，结构化工作记忆字典
    """
    _ensure_table()
    now = time.time()
    # 首条消息自动作为标题
    title = messages[0].get("content", "")[:50] if messages else ""
    sinks_json = json.dumps(attention_sinks or [], ensure_ascii=False)
    wm_json = json.dumps(working_memory or {}, ensure_ascii=False)

    conn = _get_conn()
    conn.execute(
        """
        INSERT INTO agent_threads (thread_id, messages, attention_sinks, working_memory, created_at, updated_at, title)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(thread_id) DO UPDATE SET
            messages = excluded.messages,
            attention_sinks = excluded.attention_sinks,
            working_memory = excluded.working_memory,
            updated_at = excluded.updated_at,
            title = CASE WHEN excluded.title != '' THEN excluded.title ELSE title END
        """,
        (thread_id, json.dumps(messages, ensure_ascii=False), sinks_json, wm_json, now, now, title),
    )
    conn.commit()


def load_thread(thread_id: str) -> tuple[list[dict], list[dict], dict] | None:
    """加载指定 thread 的消息历史、Attention Sink 和工作记忆

    Returns:
        (messages, attention_sinks, working_memory) 三元组
        或 None（thread 不存在）
    """
    _ensure_table()
    row = _get_conn().execute(
        "SELECT messages, attention_sinks, working_memory FROM agent_threads WHERE thread_id = ?", (thread_id,)
    ).fetchone()
    if row is None:
        return None
    messages = json.loads(row["messages"])
    sinks = json.loads(row["attention_sinks"]) if row["attention_sinks"] else []
    wm = json.loads(row["working_memory"]) if row["working_memory"] else {}
    return messages, sinks, wm


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
    """删除指定 thread 及消息历史、索引数据

    Returns:
        True（存在并删除）/ False（不存在）
    """
    _ensure_table()
    conn = _get_conn()
    cur = conn.execute(
        "DELETE FROM agent_threads WHERE thread_id = ?", (thread_id,)
    )
    # 同步清理索引
    delete_thread_index(thread_id)
    conn.commit()
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
    _ensure_index_tables()
    logger.info("持久化存储就绪 | db=%s", C.PERSISTENCE_DB_PATH)


# ═══════════════════════════════════════════════════════════════════════════════
# 索引表 — 全文搜索 + 实体索引
# ═══════════════════════════════════════════════════════════════════════════════
# 设计目标：
#   1. thread_messages: 每条消息独立一行，支持时序和按 thread_id 检索
#   2. msg_fts: FTS5 全文搜索虚拟表，支持跨会话关键词搜索
#   3. thread_entities: 按 thread 聚合的关键实体
#   4. global_entities: 跨会话实体统计（用于用户画像聚合）
# ═══════════════════════════════════════════════════════════════════════════════


_INDEX_ENSURED = False


def _ensure_index_tables():
    """确保索引表存在（幂等）"""
    global _INDEX_ENSURED
    if _INDEX_ENSURED:
        return
    conn = _get_conn()

    # 1. 独立消息表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS thread_messages (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id  TEXT NOT NULL,
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at REAL NOT NULL,
            turn_index INTEGER NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tm_thread ON thread_messages(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tm_created ON thread_messages(created_at)")

    # 2. FTS5 全文搜索虚拟表
    try:
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS msg_fts USING fts5(
                content,
                role       UNINDEXED,
                thread_id  UNINDEXED,
                tokenize='unicode61'
            )
        """)
    except sqlite3.OperationalError as e:
        logger.warning("FTS5 不可用，全文搜索降级为 LIKE 模式 | error=%s", e)

    # 3. 线程级实体表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS thread_entities (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_id  TEXT NOT NULL,
            entity     TEXT NOT NULL,
            frequency  INTEGER DEFAULT 1,
            last_seen  REAL NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_te_thread ON thread_entities(thread_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_te_entity ON thread_entities(entity)")

    # 4. 跨线程实体聚合表（用户画像）
    conn.execute("""
        CREATE TABLE IF NOT EXISTS global_entities (
            entity          TEXT PRIMARY KEY,
            total_frequency INTEGER DEFAULT 0,
            thread_count    INTEGER DEFAULT 0,
            last_seen       REAL NOT NULL
        )
    """)

    conn.commit()
    _INDEX_ENSURED = True


def index_thread_messages(thread_id: str, messages: list[dict]) -> None:
    """将 thread 的消息逐条写入索引表，供全文搜索

    策略：
      - 先删除该 thread 的旧索引数据（幂等更新）
      - 逐条写入 thread_messages + msg_fts（FTS5）

    Args:
        thread_id: 会话 ID
        messages: [{role, content}, ...] 格式的消息列表
    """
    _ensure_index_tables()
    conn = _get_conn()
    now = time.time()

    # 清理旧索引
    conn.execute("DELETE FROM thread_messages WHERE thread_id = ?", (thread_id,))
    _try_fts_delete(conn, thread_id)

    # 逐条写入
    rows: list[tuple] = []
    fts_rows: list[tuple] = []
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if not content:
            continue
        rows.append((thread_id, role, content, now, i))

    if not rows:
        return

    conn.executemany(
        "INSERT INTO thread_messages (thread_id, role, content, created_at, turn_index) VALUES (?, ?, ?, ?, ?)",
        rows,
    )

    # FTS5 写入（每条消息独立行，便于按 thread_id 删除）
    fts_rows = [(row[2], row[1], row[0]) for row in rows]  # (content, role, thread_id)
    conn.executemany(
        "INSERT INTO msg_fts (content, role, thread_id) VALUES (?, ?, ?)",
        fts_rows,
    )

    conn.commit()


def _try_fts_delete(conn: sqlite3.Connection, thread_id: str):
    """尝试从 FTS5 表删除指定 thread 的数据（FTS5 可能不可用）"""
    try:
        conn.execute("DELETE FROM msg_fts WHERE thread_id = ?", (thread_id,))
    except sqlite3.OperationalError:
        pass  # FTS5 不可用，跳过


def _has_cjk(text: str) -> bool:
    """检测文本是否包含中文字符（CJK 统一表意文字）"""
    return bool(re.search(r'[一-鿿㐀-䶿]', text))


def search_conversations(
    query: str,
    limit: int = 20,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """跨会话全文搜索

    优先使用 FTS5 加速（仅英文/ASCII 查询），
    含 CJK 字符时自动降级到 LIKE 模式（FTS5 unicode61 分词器不擅中文）。

    Args:
        query: 搜索关键词
        limit: 返回条数上限
        offset: 分页偏移

    Returns:
        [{message_id, thread_id, role, content, created_at, turn_index}, ...]
        按 created_at 倒序
    """
    _ensure_index_tables()
    conn = _get_conn()
    query = query.strip()

    if not query:
        return []

    # 含中文 → 直接 LIKE，跳过 FTS5
    if _has_cjk(query):
        return _like_search(conn, query, limit, offset)

    # 纯英文 → 尝试 FTS5，失败降级 LIKE
    fts_result = _try_fts_search(conn, query, limit, offset)
    if fts_result is not None:
        return fts_result

    logger.info("FTS5 搜索降级为 LIKE | query=%s", query)
    return _like_search(conn, query, limit, offset)


def _like_search(conn: sqlite3.Connection, query: str, limit: int, offset: int) -> list[dict]:
    """LIKE 模式搜索（中文兜底）"""
    like_pattern = f"%{query}%"
    rows = conn.execute(
        """
        SELECT id, thread_id, role, content, created_at, turn_index
        FROM thread_messages
        WHERE content LIKE ?
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
        """,
        (like_pattern, limit, offset),
    ).fetchall()
    return [_message_row_to_dict(r) for r in rows]


def _try_fts_search(conn: sqlite3.Connection, query: str, limit: int, offset: int) -> list[dict] | None:
    """尝试 FTS5 搜索，失败返回 None"""
    try:
        rows = conn.execute(
            """
            SELECT m.id, m.thread_id, m.role, m.content, m.created_at, m.turn_index
            FROM msg_fts AS f
            JOIN thread_messages AS m ON m.id = f.rowid
            WHERE msg_fts MATCH ?
            ORDER BY rank
            LIMIT ? OFFSET ?
            """,
            (query, limit, offset),
        ).fetchall()
        return [_message_row_to_dict(r) for r in rows]
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
        logger.debug("FTS5 搜索失败（降级到 LIKE）| error=%s", e)
        return None


def _message_row_to_dict(row: sqlite3.Row) -> dict:
    """将 thread_messages 行转为 dict"""
    return {
        "message_id": row["id"],
        "thread_id": row["thread_id"],
        "role": row["role"],
        "content": row["content"],
        "created_at": row["created_at"],
        "turn_index": row["turn_index"],
    }


# ── 实体索引 ──────────────────────────────────────────────────────────────


def extract_thread_entities(thread_id: str, messages: list[dict]) -> None:
    """从 thread 消息中提取关键实体并写入索引表

    提取策略（与 attention.py 的 detect_frequent_entities 类似）：
      - 英文单词（≥3 字符）
      - 中文词组（2-4 字）
      - Wiki 页面引用（`xxx.md`）
    频次 ≥ THREAD_ENTITY_MIN_FREQ 的实体才会被写入。

    Args:
        thread_id: 会话 ID
        messages: [{role, content}, ...] 格式的消息列表
    """
    import re

    _ensure_index_tables()
    conn = _get_conn()
    now = time.time()

    # 频次统计
    word_counts: dict[str, int] = {}
    for msg in messages:
        content = msg.get("content", "")
        if not content:
            continue
        # 英文单词
        for w in re.findall(r'[A-Za-z]\w{2,}', content):
            word_counts[w.lower()] = word_counts.get(w.lower(), 0) + 1
        # 中文词组
        for c in re.findall(r'[一-鿿]{2,4}', content):
            word_counts[c] = word_counts.get(c, 0) + 1
        # Wiki 引用
        for ref in re.findall(C.WIKI_PATH_REGEX, content):
            name = ref.replace(".md", "").replace("_", " ").replace("/", " ")
            word_counts[name] = word_counts.get(name, 0) + 1

    # 过滤低频并写入
    min_freq = getattr(C, "THREAD_ENTITY_MIN_FREQ", 2)
    entities = [(e, c) for e, c in word_counts.items() if c >= min_freq]
    if not entities:
        return

    # 清理旧实体
    conn.execute("DELETE FROM thread_entities WHERE thread_id = ?", (thread_id,))

    # 写入 thread_entities
    conn.executemany(
        "INSERT INTO thread_entities (thread_id, entity, frequency, last_seen) VALUES (?, ?, ?, ?)",
        [(thread_id, e, c, now) for e, c in entities],
    )

    # 合并到 global_entities
    for entity, count in entities:
        conn.execute(
            """
            INSERT INTO global_entities (entity, total_frequency, thread_count, last_seen)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(entity) DO UPDATE SET
                total_frequency = total_frequency + ?,
                thread_count    = thread_count + 1,
                last_seen       = ?
            """,
            (entity, count, now, count, now),
        )

    conn.commit()


def search_threads_by_entity(entity: str, limit: int = 20) -> list[dict[str, Any]]:
    """按实体查找关联的 thread

    Args:
        entity: 实体名称（模糊匹配）
        limit: 返回条数上限

    Returns:
        [{thread_id, entity, frequency, last_seen}, ...]
        按 frequency × thread_count 加权排序
    """
    _ensure_index_tables()
    rows = _get_conn().execute(
        """
        SELECT te.thread_id, te.entity, te.frequency, te.last_seen,
               at.title, at.updated_at
        FROM thread_entities te
        JOIN agent_threads at ON at.thread_id = te.thread_id
        WHERE te.entity LIKE ?
        ORDER BY te.frequency DESC, te.last_seen DESC
        LIMIT ?
        """,
        (f"%{entity}%", limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_global_entities(limit: int = 50, min_frequency: int = 1) -> list[dict[str, Any]]:
    """获取跨线程实体聚合统计（用户画像）

    Args:
        limit: 返回条数上限
        min_frequency: 最低频次过滤

    Returns:
        [{entity, total_frequency, thread_count, last_seen}, ...]
        按 total_frequency × thread_count 加权排序
    """
    _ensure_index_tables()
    rows = _get_conn().execute(
        """
        SELECT entity, total_frequency, thread_count, last_seen
        FROM global_entities
        WHERE total_frequency >= ?
        ORDER BY total_frequency * thread_count DESC, last_seen DESC
        LIMIT ?
        """,
        (min_frequency, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def get_thread_entities(thread_id: str, limit: int = 30) -> list[dict[str, Any]]:
    """获取指定 thread 的实体列表

    Args:
        thread_id: 会话 ID
        limit: 返回条数上限

    Returns:
        [{entity, frequency, last_seen}, ...]
    """
    _ensure_index_tables()
    rows = _get_conn().execute(
        """
        SELECT entity, frequency, last_seen
        FROM thread_entities
        WHERE thread_id = ?
        ORDER BY frequency DESC
        LIMIT ?
        """,
        (thread_id, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_thread_index(thread_id: str) -> None:
    """删除 thread 的所有索引数据"""
    _ensure_index_tables()
    conn = _get_conn()
    conn.execute("DELETE FROM thread_messages WHERE thread_id = ?", (thread_id,))
    conn.execute("DELETE FROM thread_entities WHERE thread_id = ?", (thread_id,))
    _try_fts_delete(conn, thread_id)
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# 记忆降级归档 — Memory Degradation
# ═══════════════════════════════════════════════════════════════════════════════


def get_thread_age_days(thread_id: str) -> float | None:
    """获取会话已闲置的天数

    Args:
        thread_id: 会话 ID

    Returns:
        已闲置天数，None 表示 thread 不存在
    """
    _ensure_table()
    row = _get_conn().execute(
        "SELECT updated_at FROM agent_threads WHERE thread_id = ?",
        (thread_id,),
    ).fetchone()
    if row is None:
        return None
    return (time.time() - row["updated_at"]) / 86400


def is_thread_archived(thread_id: str) -> bool:
    """检查会话是否已归档（archive_summary 列不为空）

    Args:
        thread_id: 会话 ID

    Returns:
        True 表示已归档
    """
    _ensure_table()
    row = _get_conn().execute(
        "SELECT archive_summary FROM agent_threads WHERE thread_id = ?",
        (thread_id,),
    ).fetchone()
    if row is None:
        return False
    return bool(row["archive_summary"])


def get_archive_summary(thread_id: str) -> str | None:
    """获取归档摘要文本

    Args:
        thread_id: 会话 ID

    Returns:
        摘要文本，未归档或不存在时返回 None
    """
    _ensure_table()
    row = _get_conn().execute(
        "SELECT archive_summary FROM agent_threads WHERE thread_id = ?",
        (thread_id,),
    ).fetchone()
    if row is None:
        return None
    return row["archive_summary"] if row["archive_summary"] else None


def store_archive_summary(thread_id: str, summary_text: str) -> None:
    """存储归档摘要（不修改 messages 列）

    归档只追加摘要信息，原始对话完整保留。
    用户可随时通过 load_thread() 查看完整聊天记录。

    Args:
        thread_id: 会话 ID
        summary_text: LLM 生成的对话摘要文本
    """
    _ensure_table()
    now = time.time()
    conn = _get_conn()
    conn.execute(
        """UPDATE agent_threads
           SET archive_summary = ?, updated_at = ?
           WHERE thread_id = ?""",
        (summary_text, now, thread_id),
    )
    conn.commit()


def list_stale_threads(days: int = 30, limit: int = 50) -> list[dict[str, Any]]:
    """列出超过指定天数未更新的会话

    Args:
        days: 闲置天数阈值
        limit: 返回条数上限

    Returns:
        [{thread_id, title, message_count, created_at, updated_at}, ...]
        按 updated_at 升序（最旧优先）
    """
    _ensure_table()
    cutoff = time.time() - days * 86400
    rows = _get_conn().execute(
        """
        SELECT thread_id, title, created_at, updated_at,
               json_array_length(messages) as message_count
        FROM agent_threads
        WHERE updated_at < ?
        ORDER BY updated_at ASC
        LIMIT ?
        """,
        (cutoff, limit),
    ).fetchall()
    return [dict(r) for r in rows]


