"""
数据访问层 — SQLite 操作
"""
import sqlite3
from pathlib import Path


class WikiRepository:
    """Wiki 元数据的数据访问层"""

    def __init__(self, db_path: str = "wiki.db"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """初始化数据库表"""
        from src.db.schema import CREATE_TABLES
        conn = self._get_connection()
        conn.executescript(CREATE_TABLES)
        conn.commit()
        conn.close()

    def add_page(self, path: str, title: str, page_type: str, tags: list[str] = None):
        """添加或更新页面记录"""
        raise NotImplementedError("Phase 1 实现")

    def add_link(self, source: str, target: str):
        """添加页面间链接关系"""
        raise NotImplementedError("Phase 1 实现")

    def get_page(self, path: str) -> dict:
        """获取页面信息"""
        raise NotImplementedError("Phase 1 实现")

    def search_pages(self, keyword: str) -> list[dict]:
        """搜索页面"""
        raise NotImplementedError("Phase 2 实现")

    def get_orphan_pages(self) -> list[str]:
        """获取孤儿页"""
        raise NotImplementedError("Phase 2 实现")
