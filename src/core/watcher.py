"""
Source 文件夹自动监听 — 轮询 raw/sources/ 新文件，自动触发 ingest

Phase 3 基础版：
  - 检测新文件 → 自动 ingest
  - 启动/停止/状态查询（API 控制）
  - 不检测删除（Phase 6）
  - 不检测修改（SHA256 缓存已能防止重复处理）
"""
import os
import threading
import time
from datetime import datetime

from src.core.logging_config import get_logger
from src.core.wiki_compiler import WikiCompiler

logger = get_logger("watcher")


class SourceWatcher:
    """监听 raw/sources/ 目录的文件变更，自动触发 ingest（轮询版）"""

    def __init__(
        self,
        sources_dir: str = "raw/sources",
        poll_interval: int = 10,
    ) -> None:
        """
        Args:
            sources_dir: 源文件目录路径
            poll_interval: 轮询间隔（秒）
        """
        self.sources_dir = sources_dir
        self.poll_interval = poll_interval
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._files_processed = 0
        self._last_check: str | None = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动后台轮询线程"""
        if self._running:
            logger.info("SourceWatcher 已在运行中")
            return

        if not os.path.isdir(self.sources_dir):
            logger.warning("源目录不存在，创建 | path=%s", self.sources_dir)
            os.makedirs(self.sources_dir, exist_ok=True)

        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="source-watcher",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "SourceWatcher 已启动 | dir=%s interval=%ds",
            self.sources_dir, self.poll_interval,
        )

    def stop(self) -> None:
        """停止轮询线程"""
        if not self._running:
            logger.info("SourceWatcher 未在运行")
            return

        self._running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        logger.info("SourceWatcher 已停止 | processed=%d", self._files_processed)

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """
        返回监听状态

        Returns:
            {
                "running": true,
                "watched_dir": "raw/sources/",
                "poll_interval_seconds": 10,
                "last_check": "2026-07-07T15:30:00",
                "files_processed": 5,
            }
        """
        return {
            "running": self._running,
            "watched_dir": self.sources_dir,
            "poll_interval_seconds": self.poll_interval,
            "last_check": self._last_check or "",
            "files_processed": self._files_processed,
        }

    # ------------------------------------------------------------------
    # 内部 — 轮询循环
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        """后台轮询主循环"""
        while not self._stop_event.is_set():
            try:
                self._scan_and_ingest()
            except Exception as exc:
                logger.error("SourceWatcher 扫描异常 | %s", exc)

            self._last_check = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            self._stop_event.wait(self.poll_interval)

    def _scan_and_ingest(self) -> None:
        """
        扫描目录 → 发现新文件 → 调用 WikiCompiler.ingest()

        依赖 SHA256 缓存判断是否为新内容，已处理的文件自动跳过。
        """
        if not os.path.isdir(self.sources_dir):
            logger.debug("源目录不存在，跳过扫描 | path=%s", self.sources_dir)
            return

        files = []
        for fname in os.listdir(self.sources_dir):
            if not fname.endswith(".md"):
                continue
            if fname.startswith("."):
                continue
            full = os.path.join(self.sources_dir, fname)
            if os.path.isfile(full):
                files.append(fname)

        if not files:
            return

        logger.debug("SourceWatcher 扫描到 %d 个源文件", len(files))

        for source_path in sorted(files):
            if self._stop_event.is_set():
                break

            try:
                compiler = WikiCompiler()
                result = compiler.ingest(source_path)
                if result.get("status") == "success":
                    self._files_processed += 1
                    logger.info(
                        "SourceWatcher 自动 ingest | source=%s pages=%d+%d",
                        source_path,
                        len(result.get("pages_created", [])),
                        len(result.get("pages_updated", [])),
                    )
                elif result.get("status") == "skipped":
                    logger.debug(
                        "SourceWatcher 跳过（缓存命中）| source=%s", source_path
                    )
                else:
                    logger.warning(
                        "SourceWatcher ingest 返回未知状态 | source=%s status=%s",
                        source_path, result.get("status"),
                    )
            except Exception as exc:
                logger.error(
                    "SourceWatcher ingest 失败 | source=%s error=%s",
                    source_path, exc,
                )
