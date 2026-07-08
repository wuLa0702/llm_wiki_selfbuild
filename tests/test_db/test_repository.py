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


# ============================================================================
# 搜索
# ============================================================================


def test_search_pages_by_title(repo):
    """search_pages 按标题匹配"""
    repo.add_page("entities/python.md", "Python 语言", "entity", tags=["编程"])
    repo.add_page("entities/java.md", "Java 语言", "entity", tags=["编程"])

    results = repo.search_pages("Python")
    assert len(results) >= 1
    assert results[0]["path"] == "entities/python.md"


def test_search_pages_by_path(repo):
    """search_pages 按路径匹配"""
    repo.add_page("concepts/deep_learning.md", "深度学习", "concept")

    results = repo.search_pages("deep_learning")
    assert len(results) >= 1


def test_search_pages_by_tags(repo):
    """search_pages 按标签匹配"""
    repo.add_page("entities/transformer.md", "Transformer", "entity",
                  tags=["deep-learning", "attention"])

    results = repo.search_pages("attention")
    assert len(results) >= 1


def test_search_pages_no_match(repo):
    """无匹配时返回空列表"""
    results = repo.search_pages("xyznonexistent12345")
    assert results == []


def test_search_pages_limit(repo):
    """limit 参数限制返回数量"""
    for i in range(5):
        repo.add_page(f"entities/p{i}.md", f"Python {i}", "entity")
    results = repo.search_pages("Python", limit=3)
    assert len(results) == 3


def test_search_pages_case_insensitive(repo):
    """SQLite LIKE 默认不区分大小写"""
    repo.add_page("entities/python.md", "Python Language", "entity")
    results = repo.search_pages("python")
    assert len(results) >= 1


# ============================================================================
# 4-Signal 关联度
# ============================================================================


class TestRelevance:
    """graph_relevance 表操作"""

    def test_save_and_get_related(self, repo):
        rows = [
            {"source_path": "a.md", "target_path": "b.md", "total_score": 8.5,
             "direct_link": 3.0, "source_overlap": 4.0, "adamic_adar": 0, "type_affinity": 1.5},
            {"source_path": "a.md", "target_path": "c.md", "total_score": 5.0,
             "direct_link": 0, "source_overlap": 4.0, "adamic_adar": 0, "type_affinity": 1.0},
        ]
        repo.save_relevance(rows)
        related = repo.get_related_pages("a.md", limit=10)
        assert len(related) == 2
        assert related[0]["target_path"] == "b.md"
        assert related[0]["total_score"] == 8.5

    def test_get_related_empty(self, repo):
        assert repo.get_related_pages("nonexistent.md") == []

    def test_save_relevance_upsert(self, repo):
        rows = [{
            "source_path": "a.md", "target_path": "b.md", "total_score": 3.0,
            "direct_link": 3.0, "source_overlap": 0, "adamic_adar": 0, "type_affinity": 0,
        }]
        repo.save_relevance(rows)
        rows[0]["total_score"] = 7.0
        repo.save_relevance(rows)
        related = repo.get_related_pages("a.md")
        assert related[0]["total_score"] == 7.0


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


# ============================================================================
# 搜索
# ============================================================================


def test_search_pages_by_title(repo):
    """search_pages 按标题匹配"""
    repo.add_page("entities/python.md", "Python 语言", "entity", tags=["编程"])
    repo.add_page("entities/java.md", "Java 语言", "entity", tags=["编程"])

    results = repo.search_pages("Python")
    assert len(results) >= 1
    assert results[0]["path"] == "entities/python.md"


def test_search_pages_by_path(repo):
    """search_pages 按路径匹配"""
    repo.add_page("concepts/deep_learning.md", "深度学习", "concept")

    results = repo.search_pages("deep_learning")
    assert len(results) >= 1


def test_search_pages_by_tags(repo):
    """search_pages 按标签匹配"""
    repo.add_page("entities/transformer.md", "Transformer", "entity",
                  tags=["deep-learning", "attention"])

    results = repo.search_pages("attention")
    assert len(results) >= 1


def test_search_pages_no_match(repo):
    """无匹配时返回空列表"""
    results = repo.search_pages("xyznonexistent12345")
    assert results == []


def test_search_pages_limit(repo):
    """limit 参数限制返回数量"""
    for i in range(5):
        repo.add_page(f"entities/p{i}.md", f"Python {i}", "entity")
    results = repo.search_pages("Python", limit=3)
    assert len(results) == 3


def test_search_pages_case_insensitive(repo):
    """SQLite LIKE 默认不区分大小写"""
    repo.add_page("entities/python.md", "Python Language", "entity")
    results = repo.search_pages("python")
    assert len(results) >= 1


# ============================================================================
# 4-Signal 关联度
# ============================================================================


class TestRelevance:
    """graph_relevance 表操作"""

    def test_save_and_get_related(self, repo):
        rows = [
            {"source_path": "a.md", "target_path": "b.md", "total_score": 8.5,
             "direct_link": 3.0, "source_overlap": 4.0, "adamic_adar": 0, "type_affinity": 1.5},
            {"source_path": "a.md", "target_path": "c.md", "total_score": 5.0,
             "direct_link": 0, "source_overlap": 4.0, "adamic_adar": 0, "type_affinity": 1.0},
        ]
        repo.save_relevance(rows)
        related = repo.get_related_pages("a.md", limit=10)
        assert len(related) == 2
        assert related[0]["target_path"] == "b.md"
        assert related[0]["total_score"] == 8.5

    def test_get_related_empty(self, repo):
        assert repo.get_related_pages("nonexistent.md") == []

    def test_save_relevance_upsert(self, repo):
        rows = [{
            "source_path": "a.md", "target_path": "b.md", "total_score": 3.0,
            "direct_link": 3.0, "source_overlap": 0, "adamic_adar": 0, "type_affinity": 0,
        }]
        repo.save_relevance(rows)
        rows[0]["total_score"] = 7.0
        repo.save_relevance(rows)
        related = repo.get_related_pages("a.md")
        assert related[0]["total_score"] == 7.0
