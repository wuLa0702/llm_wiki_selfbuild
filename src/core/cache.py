"""
SHA256 增量缓存 — 检测源文件是否变化，避免重复 ingest
"""
import hashlib
import os
import sqlite3

from src.utils.path_resolver import get_db_path, get_raw_sources_dir


class IngestCache:
    """基于 SHA256 的源文件增量缓存"""

    def __init__(self, db_path: str | None = None, sources_dir: str | None = None) -> None:
        """
        Args:
            db_path: SQLite 数据库路径，None 时使用 %APPDATA%/LLM-Wiki/wiki.db
            sources_dir: raw/sources 目录路径，None 时使用 %APPDATA%/LLM-Wiki/raw/sources
        """
        self.db_path = db_path if db_path is not None else get_db_path("wiki.db")
        self.sources_dir = sources_dir if sources_dir is not None else get_raw_sources_dir()
        self._init_table()

    def _init_table(self) -> None:
        """确保 ingest_cache 表存在"""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS ingest_cache ("
            "  source_path TEXT PRIMARY KEY,"
            "  sha256_hash TEXT NOT NULL,"
            "  ingested_at TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        )
        conn.commit()
        conn.close()

    def _hash_file(self, source_path: str) -> str:
        """计算源文件的 SHA256 哈希"""
        full = os.path.join(self.sources_dir, source_path)
        hasher = hashlib.sha256()
        with open(full, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    def has_changed(self, source_path: str) -> bool:
        """
        检测源文件内容是否变化

        Args:
            source_path: 相对于 sources_dir 的文件路径

        Returns:
            True — 文件已变或为新文件（需要 ingest）
            False — 文件未变（缓存命中，可跳过）
        """
        try:
            current = self._hash_file(source_path)
        except FileNotFoundError:
            return True  # 文件不存在，让调用方处理

        conn = sqlite3.connect(self.db_path)
        row = conn.execute(
            "SELECT sha256_hash FROM ingest_cache WHERE source_path = ?",
            (source_path,),
        ).fetchone()
        conn.close()

        if row and row[0] == current:
            return False
        return True

    def mark_ingested(self, source_path: str) -> None:
        """记录已 ingest 的哈希值"""
        current = self._hash_file(source_path)
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "INSERT OR REPLACE INTO ingest_cache (source_path, sha256_hash) VALUES (?, ?)",
            (source_path, current),
        )
        conn.commit()
        conn.close()
