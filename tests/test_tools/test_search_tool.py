"""
SearchTool 单元测试
"""
import os

import pytest

from src.tools.search_tool import SearchTool


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def wiki_dir(tmp_path):
    d = tmp_path / "wiki"
    d.mkdir()
    # 实体页面
    (d / "entities").mkdir()
    (d / "entities" / "python.md").write_text(
        "# Python 编程语言\n\nPython 是一种通用编程语言。\n"
        "广泛用于 AI、数据科学和 Web 开发。",
        encoding="utf-8",
    )
    (d / "entities" / "java.md").write_text(
        "# Java\n\nJava 是一种面向对象的编程语言。",
        encoding="utf-8",
    )
    # 概念页面
    (d / "concepts").mkdir()
    (d / "concepts" / "ai.md").write_text(
        "# 人工智能\n\n人工智能是模拟人类智能的技术。\n",
        encoding="utf-8",
    )
    # 导航文件（应被搜索跳过）
    (d / "index.md").write_text("# Wiki Index\n\n- [[entities/python.md]]", encoding="utf-8")
    (d / "overview.md").write_text("# Overview", encoding="utf-8")
    return d


@pytest.fixture
def tool(wiki_dir):
    return SearchTool(str(wiki_dir))


# ============================================================================
# 文件名匹配
# ============================================================================


def test_search_by_filename(tool):
    """文件名包含关键词返回 match_type=filename"""
    results = tool.search("python")
    matches = [r for r in results if r["match_type"] == "filename"]
    assert len(matches) >= 1
    assert "python.md" in matches[0]["path"]


def test_search_by_filename_multiple(tool):
    """多个文件名包含关键词"""
    results = tool.search("java")
    filenames = [r["path"] for r in results if r["match_type"] == "filename"]
    assert len(filenames) >= 1
    assert any("java.md" in p for p in filenames)


# ============================================================================
# 内容匹配
# ============================================================================


def test_search_by_content(tool):
    """内容包含关键词返回 match_type=content"""
    results = tool.search("数据科学")
    assert len(results) >= 1
    assert results[0]["match_type"] in ("title", "content")


def test_search_by_content_returns_snippet(tool):
    """内容匹配结果包含上下文片段"""
    results = tool.search("面向对象")
    assert len(results) >= 1
    # java.md 包含"面向对象"
    java_results = [r for r in results if "java.md" in r["path"]]
    assert len(java_results) >= 1
    assert "面向对象" in java_results[0]["snippet"]


# ============================================================================
# 导航文件跳过
# ============================================================================


def test_search_skips_index_file(tool):
    """搜索不返回 index.md"""
    results = tool.search("Wiki Index")
    paths = {r["path"] for r in results}
    assert "index.md" not in paths


def test_search_skips_overview_file(tool):
    """搜索不返回 overview.md"""
    results = tool.search("Overview")
    paths = {r["path"] for r in results}
    assert "overview.md" not in paths


# ============================================================================
# 边界
# ============================================================================


def test_search_no_results(tool):
    """无匹配时返回空列表"""
    results = tool.search("xyznonexistent12345")
    assert results == []


def test_search_empty_keyword(tool):
    """空关键词返回空列表"""
    assert tool.search("") == []
    assert tool.search("   ") == []


def test_search_case_insensitive(tool):
    """搜索不区分大小写"""
    results = tool.search("PYTHON")
    assert len(results) >= 1


def test_search_limit(tool):
    """limit 参数限制返回数量"""
    # 有很多包含'编程'的页面
    results = tool.search("编程", limit=1)
    assert len(results) <= 1


def test_search_sort_priority(tool):
    """排序：文件名 > 标题 > 正文"""
    results = tool.search("编程")
    # 至少有一个 filename 或 title 结果
    types = [r["match_type"] for r in results]
    if len(results) >= 2:
        # filename 应该在 title/content 之前
        prio = {"filename": 0, "title": 1, "content": 2}
        for i in range(len(types) - 1):
            assert prio[types[i]] <= prio[types[i + 1]]
