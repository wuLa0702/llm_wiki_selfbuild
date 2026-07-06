"""
IngestCache 单元测试
"""
import os
import sqlite3

import pytest

from src.core.cache import IngestCache


@pytest.fixture
def sources_dir(tmp_path):
    """创建临时源文件目录"""
    d = tmp_path / "sources"
    d.mkdir(parents=True)
    (d / "test.md").write_text("original content", encoding="utf-8")
    return d


@pytest.fixture
def cache(tmp_path, sources_dir):
    """基于临时数据库的 IngestCache"""
    return IngestCache(
        db_path=str(tmp_path / "cache.db"),
        sources_dir=str(sources_dir),
    )


class TestCache:
    def test_has_changed_new_file(self, cache, sources_dir):
        """新文件返回 True"""
        assert cache.has_changed("test.md") is True

    def test_has_changed_after_mark(self, cache, sources_dir):
        """标记后返回 False"""
        cache.mark_ingested("test.md")
        assert cache.has_changed("test.md") is False

    def test_has_changed_after_modification(self, cache, sources_dir):
        """修改文件后返回 True"""
        cache.mark_ingested("test.md")
        (sources_dir / "test.md").write_text("modified content", encoding="utf-8")
        assert cache.has_changed("test.md") is True

    def test_has_changed_file_not_found(self, cache):
        """不存在的文件返回 True（不抛异常）"""
        assert cache.has_changed("nonexistent.md") is True

    def test_mark_ingested_multiple(self, cache, sources_dir):
        """多次标记不同文件"""
        (sources_dir / "a.md").write_text("a")
        (sources_dir / "b.md").write_text("b")
        cache.mark_ingested("a.md")
        cache.mark_ingested("b.md")
        assert cache.has_changed("a.md") is False
        assert cache.has_changed("b.md") is False

    def test_mark_ingested_overwrites_old_hash(self, cache, sources_dir):
        """重新标记同一文件覆盖旧哈希"""
        cache.mark_ingested("test.md")
        old_hash = self._get_hash(cache, "test.md")
        (sources_dir / "test.md").write_text("new content")
        cache.mark_ingested("test.md")
        new_hash = self._get_hash(cache, "test.md")
        assert old_hash != new_hash
        assert cache.has_changed("test.md") is False

    def test_hash_differs_for_different_content(self, cache, sources_dir):
        """不同内容产生不同的哈希"""
        (sources_dir / "a.md").write_text("hello")
        (sources_dir / "b.md").write_text("world")
        h1 = cache._hash_file("a.md")
        h2 = cache._hash_file("b.md")
        assert h1 != h2

    @staticmethod
    def _get_hash(cache, source_path):
        conn = sqlite3.connect(cache.db_path)
        row = conn.execute(
            "SELECT sha256_hash FROM ingest_cache WHERE source_path = ?",
            (source_path,),
        ).fetchone()
        conn.close()
        return row[0] if row else None
