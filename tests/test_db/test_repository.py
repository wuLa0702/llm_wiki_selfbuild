"""
WikiRepository 单元测试
"""
import sqlite3

import pytest

from src.db.repository import WikiRepository


@pytest.fixture
def repo(tmp_path):
    """创建使用临时数据库的 WikiRepository"""
    db_path = str(tmp_path / "test.db")
    return WikiRepository(db_path=db_path)


# ---------------------------------------------------------------------------
# 正常路径 — 页面 CRUD
# ---------------------------------------------------------------------------


def test_add_and_get_page(repo):
    """添加页面后能正确查询"""
    repo.add_page("entities/python.md", "Python", "entity", tags=["编程", "AI"])

    page = repo.get_page("entities/python.md")
    assert page is not None
    assert page["path"] == "entities/python.md"
    assert page["title"] == "Python"
    assert page["page_type"] == "entity"
    assert "编程" in page["tags"]
    assert "AI" in page["tags"]


def test_add_page_upsert(repo):
    """再次添加同一路径的页面会更新记录（UPSERT）"""
    repo.add_page("entities/rust.md", "Rust Lang", "entity", tags=["old"])
    repo.add_page("entities/rust.md", "Rust", "entity", tags=["systems", "safe"])

    page = repo.get_page("entities/rust.md")
    assert page["title"] == "Rust"
    assert page["tags"] == ["systems", "safe"]


def test_get_page_nonexistent(repo):
    """查询不存在的页面返回 None"""
    page = repo.get_page("nonexistent.md")
    assert page is None


# ---------------------------------------------------------------------------
# 正常路径 — 链接
# ---------------------------------------------------------------------------


def test_add_link_and_backlinks(repo):
    """添加链接后 get_page 返回正确的 backlinks"""
    repo.add_page("entities/a.md", "A", "entity")
    repo.add_page("entities/b.md", "B", "entity")
    repo.add_page("entities/c.md", "C", "entity")

    repo.add_link("entities/b.md", "entities/a.md")
    repo.add_link("entities/c.md", "entities/a.md")

    page = repo.get_page("entities/a.md")
    assert sorted(page["backlinks"]) == ["entities/b.md", "entities/c.md"]


def test_add_link_forward_links(repo):
    """get_page 也返回正向链接"""
    repo.add_page("entities/a.md", "A", "entity")
    repo.add_page("entities/b.md", "B", "entity")

    repo.add_link("entities/a.md", "entities/b.md")

    page = repo.get_page("entities/a.md")
    assert "entities/b.md" in page["links"]


def test_add_link_duplicate_ignored(repo):
    """重复添加同一链接不会抛异常"""
    repo.add_page("entities/a.md", "A", "entity")
    repo.add_page("entities/b.md", "B", "entity")

    repo.add_link("entities/a.md", "entities/b.md")
    repo.add_link("entities/a.md", "entities/b.md")  # 重复，应静默忽略

    page = repo.get_page("entities/a.md")
    assert len(page["links"]) == 1  # 不会重复


# ---------------------------------------------------------------------------
# 边界条件
# ---------------------------------------------------------------------------


def test_add_page_empty_tags(repo):
    """tags 为空时默认为空列表"""
    repo.add_page("entities/empty.md", "Empty", "concept")
    page = repo.get_page("entities/empty.md")
    assert page["tags"] == []


def test_add_page_word_count(repo):
    """word_count 被正确存储"""
    repo.add_page("entities/long.md", "Long", "concept", word_count=1200)
    page = repo.get_page("entities/long.md")
    assert page["word_count"] == 1200


# ---------------------------------------------------------------------------
# 操作日志
# ---------------------------------------------------------------------------


def test_add_page_logs_operation(repo):
    """add_page 会自动写入 operation_log"""
    repo.add_page("entities/logged.md", "Logged", "entity")

    conn = sqlite3.connect(repo.db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM operation_log WHERE action = ?", ("add_page",)
    ).fetchall()
    conn.close()

    assert len(rows) >= 1


def test_add_link_logs_operation(repo):
    """add_link 会自动写入 operation_log"""
    repo.add_page("entities/a.md", "A", "entity")
    repo.add_page("entities/b.md", "B", "entity")
    repo.add_link("entities/a.md", "entities/b.md")

    conn = sqlite3.connect(repo.db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM operation_log WHERE action = ?", ("add_link",)
    ).fetchall()
    conn.close()

    assert len(rows) >= 1
