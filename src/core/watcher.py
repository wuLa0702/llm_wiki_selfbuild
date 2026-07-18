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
from src.core.compiler import WikiCompiler

logger = get_logger("watcher")


class SourceWatcher:
    """监听 raw/sources/ 目录的文件变更，自动触发 ingest（轮询版）"""

    def __init__(
        self,
        sources_dir: str = "raw/sources",
        poll_interval: int = 10,
        task_queue=None,
    ) -> None:
        """
        Args:
            sources_dir: 源文件目录路径
            poll_interval: 轮询间隔（秒）
            task_queue: 可选的 TaskQueue 实例，用于 ingest 后异步重建图谱
        """
        self.sources_dir = sources_dir
        self.poll_interval = poll_interval
        self.task_queue = task_queue
        self._running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._files_processed = 0
        self._last_check: str | None = None
        self.config = self._load_config()

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

    def _load_config(self) -> dict:
        """从 DB 加载资料监控配置"""
        from src.db.repository import WikiRepository
        import json
        repo = WikiRepository()
        cfg = {
            "enabled": True, "auto_extract": True, "max_size_mb": 100,
            "allowed_ext": {".md",".txt",".pdf",".html",".htm",".csv"},
            "exclude_folders": {".git","__pycache__","node_modules"},
            "exclude_ext": {"tmp","bak","exe","dll","iso"},
            "exclude_patterns": [],
        }
        raw = repo.get_setting("settings.watcher_enabled")
        if raw is not None:
            try: cfg["enabled"] = json.loads(raw)
            except: pass
        raw = repo.get_setting("settings.watcher_auto_extract")
        if raw is not None:
            try: cfg["auto_extract"] = json.loads(raw)
            except: pass
        raw = repo.get_setting("settings.watcher_max_file_size_mb")
        if raw is not None:
            try: cfg["max_size_mb"] = int(json.loads(raw))
            except: pass
        raw = repo.get_setting("settings.watcher_allowed_extensions")
        if raw:
            try:
                v = json.loads(raw)
                if v: cfg["allowed_ext"] = {x.strip().lower() for x in v.split(",") if x.strip()}
            except: pass
        raw = repo.get_setting("settings.watcher_exclude_folders")
        if raw:
            try:
                v = json.loads(raw)
                if v: cfg["exclude_folders"] = {x.strip().lower() for x in v.split(",") if x.strip()}
            except: pass
        raw = repo.get_setting("settings.watcher_exclude_extensions")
        if raw:
            try:
                v = json.loads(raw)
                if v: cfg["exclude_ext"] = {x.strip().lower().lstrip(".") for x in v.split(",") if x.strip()}
            except: pass
        raw = repo.get_setting("settings.watcher_exclude_patterns")
        if raw:
            try:
                v = json.loads(raw)
                if v: cfg["exclude_patterns"] = [x.strip() for x in v.split(",") if x.strip()]
            except: pass
        return cfg

    def _matches_exclude_pattern(self, name: str) -> bool:
        """检查文件名是否命中模糊排除规则"""
        import fnmatch
        for pat in self.config.get("exclude_patterns", []):
            if fnmatch.fnmatch(name, pat):
                return True
        return False

    def _scan_and_ingest(self) -> None:
        """
        扫描目录 → 发现新文件 → 调用 WikiCompiler.ingest()

        依赖 SHA256 缓存判断是否为新内容，已处理的文件自动跳过。
        """
        self.config = self._load_config()
        if not self.config.get("enabled", True):
            return
        if not os.path.isdir(self.sources_dir):
            logger.debug("源目录不存在，跳过扫描 | path=%s", self.sources_dir)
            return

        allowed_ext = self.config.get("allowed_ext", {".md"})
        exclude_ext = self.config.get("exclude_ext", set())
        exclude_folders = self.config.get("exclude_folders", set())
        max_bytes = self.config.get("max_size_mb", 100) * 1024 * 1024

        files = []
        for root, dirs, fnames in os.walk(self.sources_dir):
            # 跳过排除目录
            dirs[:] = [d for d in dirs if d.lower() not in exclude_folders]
            for fname in fnames:
                if fname.startswith("."):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext not in allowed_ext:
                    continue
                bare_ext = ext.lstrip(".")
                if bare_ext in exclude_ext:
                    continue
                if self._matches_exclude_pattern(fname):
                    continue
                full = os.path.join(root, fname)
                if not os.path.isfile(full):
                    continue
                if os.path.getsize(full) > max_bytes:
                    logger.debug("文件超限，跳过 | path=%s size=%d", full, os.path.getsize(full))
                    continue
                rel = os.path.relpath(full, self.sources_dir).replace("\\", "/")
                files.append(rel)

        if not files:
            return

        logger.debug("SourceWatcher 扫描到 %d 个源文件", len(files))

        for source_path in sorted(files):
            if self._stop_event.is_set():
                break

            try:
                compiler = WikiCompiler(task_queue=self.task_queue)
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
