"""
持久化摄入队列 — Phase 4 Step 7

用于文件夹批量导入时串行处理 ingest 操作，支持崩溃恢复、重试、取消。

与 task_queue 的区别：
  task_queue：通用异步任务（图谱重建等），处理器注册模式
  ingest_queue：专门串行化 ingest 操作，内嵌 WikiCompiler 调用，支持重试
"""
import json
import os
import sqlite3
import threading
import time
from uuid import uuid4

from src.core.logging_config import get_logger
from src.core.wiki_compiler import WikiCompiler

logger = get_logger("ingest_queue")


class IngestQueue:
    """持久化摄入队列 — 串行处理 + 崩溃恢复 + 重试"""

    def __init__(
        self,
        db_path: str = "wiki.db",
        poll_interval: float = 1.0,
        task_queue=None,
    ) -> None:
        """
        Args:
            db_path: SQLite 数据库路径
            poll_interval: 轮询间隔（秒）
            task_queue: 可选的 TaskQueue 实例，ingest 后异步重建图谱
        """
        self.db_path = db_path
        self.poll_interval = poll_interval
        self.task_queue = task_queue
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._ensure_table()
        self._recover_processing()

    # ------------------------------------------------------------------
    # 表管理
    # ------------------------------------------------------------------

    def _ensure_table(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ingest_queue (
                job_id TEXT PRIMARY KEY,
                source_path TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                context TEXT DEFAULT '{}',
                result_summary TEXT DEFAULT '',
                error TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        conn.close()

    def _recover_processing(self) -> None:
        """崩溃恢复：将 processing 状态的任务重置为 pending"""
        conn = sqlite3.connect(self.db_path)
        updated = conn.execute(
            "UPDATE ingest_queue SET status='pending', updated_at=datetime('now') WHERE status='processing'"
        ).rowcount
        conn.commit()
        conn.close()
        if updated:
            logger.info("崩溃恢复：%d 个进行中任务重置为 pending", updated)

    # ------------------------------------------------------------------
    # 队列操作
    # ------------------------------------------------------------------

    def enqueue(self, source_path: str, context: dict | None = None) -> str:
        """
        加入摄入队列

        Args:
            source_path: 源文件路径（相对于 raw/sources/）
            context: 上下文信息（如 {"folder": "llm-papers"}）

        Returns:
            job_id
        """
        job_id = uuid4().hex[:12]
        context_str = json.dumps(context or {}, ensure_ascii=False)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT INTO ingest_queue (job_id, source_path, status, context) VALUES (?, ?, 'pending', ?)",
            (job_id, source_path, context_str),
        )
        conn.commit()
        conn.close()
        logger.info("摄入任务入队 | job_id=%s source=%s", job_id, source_path)
        return job_id

    def status(self, job_id: str) -> dict | None:
        """查询任务状态"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM ingest_queue WHERE job_id = ?", (job_id,)
        ).fetchone()
        conn.close()
        if row is None:
            return None
        return dict(row)

    def cancel(self, job_id: str) -> bool:
        """取消待处理的任务"""
        conn = sqlite3.connect(self.db_path)
        updated = conn.execute(
            "UPDATE ingest_queue SET status='cancelled', updated_at=datetime('now') WHERE job_id=? AND status='pending'",
            (job_id,),
        ).rowcount
        conn.commit()
        conn.close()
        return updated > 0

    def retry(self, job_id: str) -> bool:
        """重试失败的任务"""
        conn = sqlite3.connect(self.db_path)
        updated = conn.execute(
            "UPDATE ingest_queue SET status='pending', error='', updated_at=datetime('now') WHERE job_id=? AND status='failed'",
            (job_id,),
        ).rowcount
        conn.commit()
        conn.close()
        return updated > 0

    def progress(self) -> dict:
        """
        返回队列进度统计

        Returns:
            {total, pending, processing, done, failed, cancelled}
        """
        conn = sqlite3.connect(self.db_path)
        rows = conn.execute(
            "SELECT status, COUNT(*) as n FROM ingest_queue GROUP BY status"
        ).fetchall()
        conn.close()

        stats = {"total": 0, "pending": 0, "processing": 0, "done": 0, "failed": 0, "cancelled": 0}
        for r in rows:
            key = r[0]
            count = r[1]
            if key in stats:
                stats[key] = count
            stats["total"] += count
        return stats

    # ------------------------------------------------------------------
    # 任务处理
    # ------------------------------------------------------------------

    def process_next(self) -> dict | None:
        """
        处理队列中下一个 pending 任务（串行）

        Returns:
            处理结果 dict，无待处理任务返回 None
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM ingest_queue WHERE status='pending' ORDER BY created_at ASC LIMIT 1"
        ).fetchone()

        if row is None:
            conn.close()
            return None

        task = dict(row)
        job_id = task["job_id"]
        source_path = task["source_path"]

        # 标记 processing
        conn.execute(
            "UPDATE ingest_queue SET status='processing', updated_at=datetime('now') WHERE job_id=?",
            (job_id,),
        )
        conn.commit()
        conn.close()

        logger.info("开始处理摄入任务 | job_id=%s source=%s", job_id, source_path)

        try:
            compiler = WikiCompiler(task_queue=self.task_queue)
            result = compiler.ingest(source_path)

            summary = (
                f"{len(result.get('pages_created', []))} created, "
                f"{len(result.get('pages_updated', []))} updated"
            )

            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "UPDATE ingest_queue SET status='done', result_summary=?, updated_at=datetime('now') WHERE job_id=?",
                (summary, job_id),
            )
            conn.commit()
            conn.close()

            logger.info("摄入任务完成 | job_id=%s %s", job_id, summary)
            return {"job_id": job_id, "status": "done", "summary": summary}

        except Exception as exc:
            error_msg = str(exc)
            logger.error("摄入任务失败 | job_id=%s error=%s", job_id, error_msg)

            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "UPDATE ingest_queue SET status='failed', error=?, updated_at=datetime('now') WHERE job_id=?",
                (error_msg, job_id),
            )
            conn.commit()
            conn.close()

            return {"job_id": job_id, "status": "failed", "error": error_msg}

    # ------------------------------------------------------------------
    # 后台工作线程
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动后台工作线程"""
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop, name="ingest-queue", daemon=True
        )
        self._thread.start()
        logger.info("IngestQueue 工作线程已启动")

    def stop(self) -> None:
        """停止后台工作线程"""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        logger.info("IngestQueue 工作线程已停止")

    def _worker_loop(self) -> None:
        """后台轮询，串行处理任务"""
        while not self._stop_event.is_set():
            try:
                self.process_next()
            except Exception as exc:
                logger.error("IngestQueue 工作循环异常 | %s", exc)
            self._stop_event.wait(self.poll_interval)
