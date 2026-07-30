"""
轻量持久化任务队列 — SQLite 存储 + 后台线程串行处理

用于 ingest 后重建图谱、关联度计算等异步任务。
保证串行执行，支持崩溃恢复。
"""
import json
import threading
import time
from collections.abc import Callable
from datetime import datetime
from uuid import uuid4

from src.core.logging_config import get_logger
from src.utils.path_resolver import get_db_path

logger = get_logger("task_queue")

TASK_TYPES = {"rebuild_graph", "semantic_lint"}


class TaskQueue:
    """轻量持久化任务队列 — SQLite 存储 + 后台线程串行处理"""

    def __init__(self, db_path: str | None = None, poll_interval: float = 1.0) -> None:
        """
        Args:
            db_path: SQLite 数据库路径，None 时使用 %APPDATA%/LLM-Wiki/wiki.db
            poll_interval: 轮询间隔（秒）
        """
        self.db_path = db_path if db_path is not None else get_db_path("wiki.db")
        self.poll_interval = poll_interval
        self._handlers: dict[str, Callable] = {}
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ensure_table()
        self._recover_processing_tasks()

    # ------------------------------------------------------------------
    # 表管理
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        """确保 task_queue 表存在"""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_queue (
                task_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                payload TEXT DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'pending',
                error TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        conn.close()

    def _recover_processing_tasks(self) -> None:
        """崩溃恢复：将 processing 的任务重置为 pending"""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        updated = conn.execute(
            """
            UPDATE task_queue SET status = 'pending', updated_at = datetime('now')
            WHERE status = 'processing'
            """
        ).rowcount
        conn.commit()
        conn.close()
        if updated:
            logger.info("崩溃恢复：%d 个任务重置为 pending", updated)

    # ------------------------------------------------------------------
    # 处理器注册
    # ------------------------------------------------------------------

    def register_handler(self, task_type: str, handler: callable) -> None:
        """
        注册任务处理器

        Args:
            task_type: 任务类型标识
            handler: 处理函数，签名 def handler(task: dict) -> None
                     抛异常表示失败
        """
        if task_type not in TASK_TYPES and task_type != "__test__":
            logger.warning("注册未知任务类型 | type=%s", task_type)
        self._handlers[task_type] = handler

    # ------------------------------------------------------------------
    # 队列操作
    # ------------------------------------------------------------------

    def enqueue(self, task_type: str, payload: dict | None = None) -> str:
        """
        加入任务队列

        如果同类任务已有 pending 状态，不重复入队（去重）。

        Args:
            task_type: 任务类型
            payload: 任务参数

        Returns:
            task_id: 任务 ID，如果去重跳过则返回已有任务的 ID
        """
        import sqlite3

        payload_str = json.dumps(payload or {}, ensure_ascii=False)

        conn = sqlite3.connect(self.db_path)

        # 去重：同类型的 pending 任务跳过
        existing = conn.execute(
            "SELECT task_id FROM task_queue WHERE task_type = ? AND status = 'pending'",
            (task_type,),
        ).fetchone()
        if existing:
            conn.close()
            logger.debug("任务去重跳过 | type=%s task_id=%s", task_type, existing[0])
            return existing[0]

        task_id = uuid4().hex[:12]
        conn.execute(
            """
            INSERT INTO task_queue (task_id, task_type, payload, status)
            VALUES (?, ?, ?, 'pending')
            """,
            (task_id, task_type, payload_str),
        )
        conn.commit()
        conn.close()

        logger.info("任务入队 | type=%s task_id=%s", task_type, task_id)
        return task_id

    def status(self, task_id: str) -> dict | None:
        """查询任务状态"""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT * FROM task_queue WHERE task_id = ?", (task_id,)
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return dict(row)

    def cancel(self, task_id: str) -> bool:
        """取消待处理的任务"""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        updated = conn.execute(
            "UPDATE task_queue SET status = 'cancelled', updated_at = datetime('now') "
            "WHERE task_id = ? AND status = 'pending'",
            (task_id,),
        ).rowcount
        conn.commit()
        conn.close()
        return updated > 0

    def progress(self) -> dict:
        """返回队列进度统计"""
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            """
            SELECT status, COUNT(*) as n FROM task_queue GROUP BY status
            """
        ).fetchall()
        conn.close()

        stats = {"total": 0, "pending": 0, "processing": 0, "done": 0, "failed": 0, "cancelled": 0}
        for r in rows:
            key = r["status"]
            count = r["n"]
            stats[key] = count
            stats["total"] += count
        return stats

    # ------------------------------------------------------------------
    # 后台工作线程
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动后台工作线程"""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, name="task-queue", daemon=True)
        self._thread.start()
        logger.info("TaskQueue 工作线程已启动")

    def stop(self) -> None:
        """停止后台工作线程"""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        logger.info("TaskQueue 工作线程已停止")

    def _worker_loop(self) -> None:
        """后台轮询，串行处理任务"""
        import sqlite3

        while not self._stop_event.is_set():
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    """
                    SELECT * FROM task_queue
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    LIMIT 1
                    """
                ).fetchone()
                conn.close()

                if row is None:
                    self._stop_event.wait(self.poll_interval)
                    continue

                task = dict(row)
                self._execute(task)
            except Exception as exc:
                logger.error("TaskQueue 工作循环异常 | %s", exc)
                self._stop_event.wait(1)

    def _execute(self, task: dict) -> None:
        """
        执行单个任务

        1. 标记 processing
        2. 调用注册的 handler
        3. 标记 done 或 failed
        """
        import sqlite3

        task_id = task["task_id"]
        task_type = task["task_type"]
        logger.info("任务开始处理 | type=%s task_id=%s", task_type, task_id)

        # 标记 processing
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "UPDATE task_queue SET status = 'processing', updated_at = datetime('now') WHERE task_id = ?",
            (task_id,),
        )
        conn.commit()
        conn.close()

        # 执行
        handler = self._handlers.get(task_type)
        if handler is None:
            logger.warning("无处理器注册 | type=%s task_id=%s", task_type, task_id)
            self._mark_done(task_id, "done")
            return

        try:
            payload = json.loads(task.get("payload", "{}"))
            handler(payload)
            self._mark_done(task_id, "done")
            logger.info("任务完成 | type=%s task_id=%s", task_type, task_id)
        except Exception as exc:
            logger.error("任务失败 | type=%s task_id=%s error=%s", task_type, task_id, exc)
            self._mark_done(task_id, "failed", str(exc))

    def _mark_done(self, task_id: str, status: str, error: str = "") -> None:
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        if error:
            conn.execute(
                "UPDATE task_queue SET status = ?, error = ?, updated_at = datetime('now') WHERE task_id = ?",
                (status, error, task_id),
            )
        else:
            conn.execute(
                "UPDATE task_queue SET status = ?, updated_at = datetime('now') WHERE task_id = ?",
                (status, task_id),
            )
        conn.commit()
        conn.close()
