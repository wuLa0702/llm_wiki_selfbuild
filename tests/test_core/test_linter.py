"""
LintTool 单元测试 — Phase 3 静态 Lint 检查

覆盖：
- 断链检测（broken links）
- 孤页检测（orphan pages）
- Index 缺失检测（index gaps）
- 健康评分（health score）
- 边界条件：空 wiki、HTTP 链接、导航文件
"""
import os

import pytest

from src.core.linter import LintTool


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def wiki_dir(tmp_path):
    """创建模拟 wiki 目录，包含断链、孤页和正常页面"""
    d = tmp_path / "wiki"
    d.mkdir()

    # 实体页面
    (d / "entities").mkdir()
    (d / "entities" / "python.md").write_text(
        "---\ntitle: Python\ntype: entity\n---\n"
        "# Python\n\n"
        "[[concepts/ai.md|AI]] 是一种技术。\n"
        "参考 [[entities/java.md|Java]]。\n"
        "外部链接 [[https://example.com]] 不处理。\n"
        "断链 [[entities/nonexistent.md]] 不应该存在。",
        encoding="utf-8",
    )
    (d / "entities" / "java.md").write_text(
        "---\ntitle: Java\ntype: entity\n---\n"
        "# Java\n\n[[concepts/ai.md]]",
        encoding="utf-8",
    )

    # 孤页 — 没有被任何页面引用
    (d / "entities" / "orphan.md").write_text(
        "---\ntitle: Orphan\ntype: entity\n---\n"
        "# Orphan\n\n无人引用我。",
        encoding="utf-8",
    )

    # 概念页面
    (d / "concepts").mkdir()
    (d / "concepts" / "ai.md").write_text(
        "---\ntitle: AI\ntype: concept\n---\n"
        "# AI\n\n[[entities/python.md]]",
        encoding="utf-8",
    )

    # 另一个断链：指向不存在的概念页
    (d / "concepts" / "ml.md").write_text(
        "---\ntitle: ML\ntype: concept\n---\n"
        "# ML\n\n"
        "[[entities/python.md|Python]]\n"
        "[[concepts/nonexistent.md|不存在]]"
        "[[https://external.link]]",
        encoding="utf-8",
    )

    # 导航文件
    (d / "index.md").write_text(
        "# Index\n\n"
        "[[entities/python.md]]\n"
        "[[entities/java.md]]\n"
        "[[concepts/ai.md]]\n"
        "[[concepts/ml.md]]\n"
        "[[queries/sample.md]]\n",
        encoding="utf-8",
    )
    (d / "overview.md").write_text(
        "# Overview\n\n[[entities/python.md]]",
        encoding="utf-8",
    )
    (d / "log.md").write_text(
        "# Log\n\n- 2026-07-07 ingest [[entities/python.md]]",
        encoding="utf-8",
    )

    # index 缺失：新页面未加入 index
    (d / "queries").mkdir()
    (d / "queries" / "sample.md").write_text(
        "---\ntitle: Sample Query\ntype: query\n---\n"
        "# Sample\n\n[[entities/python.md]]",
        encoding="utf-8",
    )

    return d


# ============================================================================
# 断链检测
# ============================================================================


class TestCheckBrokenLinks:
    """断链检测"""

    def test_detects_broken_links(self, wiki_dir):
        """检测出指向不存在页面的 wikilinks"""
        linter = LintTool(str(wiki_dir))
        broken = linter.check_broken_links()
        targets = {b["broken_target"] for b in broken}
        assert "entities/nonexistent.md" in targets
        assert "concepts/nonexistent.md" in targets

    def test_broken_links_include_source(self, wiki_dir):
        """断链结果包含来源页面"""
        linter = LintTool(str(wiki_dir))
        broken = linter.check_broken_links()
        sources = {b["source_page"] for b in broken}
        assert "entities/python.md" in sources
        assert "concepts/ml.md" in sources

    def test_skips_http_links(self, wiki_dir):
        """HTTP/HTTPS 外部链接不被标记为断链"""
        linter = LintTool(str(wiki_dir))
        broken = linter.check_broken_links()
        targets = {b["broken_target"] for b in broken}
        # https://example.com 和 https://external.link 是外部链接
        assert "https://example.com" not in targets
        assert "https://external.link" not in targets

    def test_valid_links_not_report(self, wiki_dir):
        """指向已存在页面的链接不被标记为断链"""
        linter = LintTool(str(wiki_dir))
        broken = linter.check_broken_links()
        targets = {b["broken_target"] for b in broken}
        assert "concepts/ai.md" not in targets
        assert "entities/python.md" not in targets
        assert "entities/java.md" not in targets

    def test_no_broken_links_empty_wiki(self, tmp_path):
        """空 wiki 无断链"""
        d = tmp_path / "empty"
        d.mkdir()
        linter = LintTool(str(d))
        assert linter.check_broken_links() == []


# ============================================================================
# 孤页检测
# ============================================================================


class TestCheckOrphanPages:
    """孤页检测"""

    def test_detects_orphans(self, wiki_dir):
        """检测入度为 0 的页面（排除导航文件）"""
        linter = LintTool(str(wiki_dir))
        orphans = linter.check_orphan_pages()
        assert "entities/orphan.md" in orphans

    def test_excludes_nav_files(self, wiki_dir):
        """index.md / overview.md / log.md 不被标记为孤页"""
        linter = LintTool(str(wiki_dir))
        orphans = linter.check_orphan_pages()
        assert "index.md" not in orphans
        assert "overview.md" not in orphans
        assert "log.md" not in orphans

    def test_referenced_pages_not_orphan(self, wiki_dir):
        """被引用的页面不是孤页"""
        linter = LintTool(str(wiki_dir))
        orphans = linter.check_orphan_pages()
        assert "entities/python.md" not in orphans  # 被多个页面引用
        assert "concepts/ai.md" not in orphans  # 被 python.md 和 java.md 引用

    def test_no_orphans_when_all_linked(self, tmp_path):
        """所有页面都有入链时无孤页"""
        d = tmp_path / "linked"
        d.mkdir()
        (d / "a.md").write_text("# A\n\n[[b.md]]", encoding="utf-8")
        (d / "b.md").write_text("# B\n\n[[a.md]]", encoding="utf-8")
        linter = LintTool(str(d))
        assert linter.check_orphan_pages() == []

    def test_empty_wiki_no_orphans(self, tmp_path):
        """空 wiki 无孤页"""
        d = tmp_path / "empty"
        d.mkdir()
        linter = LintTool(str(d))
        assert linter.check_orphan_pages() == []


# ============================================================================
# Index 缺口检测
# ============================================================================


class TestCheckIndexGaps:
    """Index 缺失检测"""

    def test_detects_index_gaps(self, wiki_dir):
        """index.md 中未引用的页面被标记"""
        linter = LintTool(str(wiki_dir))
        gaps = linter.check_index_gaps()
        # orphan.md 在 index.md 中没有被引用
        assert "entities/orphan.md" in gaps

    def test_excludes_nav_files_from_gaps(self, wiki_dir):
        """index.md / overview.md / log.md 自身不是缺口"""
        linter = LintTool(str(wiki_dir))
        gaps = linter.check_index_gaps()
        assert "index.md" not in gaps
        assert "overview.md" not in gaps
        assert "log.md" not in gaps

    def test_all_pages_in_index_no_gaps(self, tmp_path):
        """所有页面都在 index.md 中时无缺口"""
        d = tmp_path / "complete"
        d.mkdir()
        (d / "entities").mkdir()
        (d / "entities" / "a.md").write_text("# A\n", encoding="utf-8")
        (d / "index.md").write_text(
            "# Index\n\n[[entities/a.md]]\n",
            encoding="utf-8",
        )
        linter = LintTool(str(d))
        gaps = linter.check_index_gaps()
        assert "entities/a.md" not in gaps

    def test_no_index_file_no_gaps(self, tmp_path):
        """index.md 不存在时返回空列表（不是错误）"""
        d = tmp_path / "no_index"
        d.mkdir()
        (d / "a.md").write_text("# A\n", encoding="utf-8")
        linter = LintTool(str(d))
        assert linter.check_index_gaps() == []


# ============================================================================
# 健康评分
# ============================================================================


class TestHealthScore:
    """健康评分"""

    def test_perfect_score(self, tmp_path):
        """完全健康的 wiki 评分 100"""
        d = tmp_path / "healthy"
        d.mkdir()
        (d / "a.md").write_text("# A\n\n[[b.md]]", encoding="utf-8")
        (d / "b.md").write_text("# B\n\n[[a.md]]", encoding="utf-8")
        (d / "index.md").write_text(
            "# Index\n\n[[a.md]]\n[[b.md]]\n",
            encoding="utf-8",
        )
        linter = LintTool(str(d))
        result = linter.run_all()
        assert result["health_score"] == 100
        assert "健康" in result["summary"]

    def test_score_deducts_for_broken_links(self, wiki_dir):
        """每个断链 -5 分"""
        linter = LintTool(str(wiki_dir))
        result = linter.run_all()
        # 2 个断链，1 个孤页：100 - 10 - 10 = 80
        expected = 100 - 5 * result["broken_links_count"]
        expected -= 10 * result["orphan_pages_count"]
        expected -= 3 * result["index_gaps_count"]
        assert result["health_score"] == expected

    def test_score_min_zero(self, tmp_path):
        """评分不低于 0"""
        d = tmp_path / "messy"
        d.mkdir()
        # 创建 30 个断链 → 扣 150 分 → 最低 0
        (d / "a.md").write_text(
            "# A\n" + "\n".join(f"[[p{i}.md]]" for i in range(30)),
            encoding="utf-8",
        )
        (d / "index.md").write_text("# Index\n\n[[a.md]]\n", encoding="utf-8")
        linter = LintTool(str(d))
        result = linter.run_all()
        assert result["health_score"] == 0


# ============================================================================
# run_all 完整结果
# ============================================================================


class TestRunAll:
    """集成测试"""

    def test_run_all_structure(self, wiki_dir):
        """run_all() 返回完整结构"""
        linter = LintTool(str(wiki_dir))
        result = linter.run_all()
        assert "broken_links" in result
        assert "broken_links_count" in result
        assert "orphan_pages" in result
        assert "orphan_pages_count" in result
        assert "index_gaps" in result
        assert "index_gaps_count" in result
        assert "health_score" in result
        assert "summary" in result

    def test_run_all_counts_match(self, wiki_dir):
        """计数与列表长度一致"""
        linter = LintTool(str(wiki_dir))
        result = linter.run_all()
        assert result["broken_links_count"] == len(result["broken_links"])
        assert result["orphan_pages_count"] == len(result["orphan_pages"])
        assert result["index_gaps_count"] == len(result["index_gaps"])

    def test_run_all_empty_wiki(self, tmp_path):
        """空 wiki 的 run_all 返回合理值"""
        d = tmp_path / "empty"
        d.mkdir()
        linter = LintTool(str(d))
        result = linter.run_all()
        assert result["broken_links"] == []
        assert result["orphan_pages"] == []
        assert result["index_gaps"] == []
        assert result["health_score"] == 100


# ============================================================================
# 边界条件
# ============================================================================


class TestEdgeCases:
    """边界条件"""

    def test_wiki_dir_not_exist(self, tmp_path):
        """wiki 目录不存在时不影响使用"""
        linter = LintTool(str(tmp_path / "nonexistent"))
        result = linter.run_all()
        assert result["health_score"] == 100
        assert result["broken_links"] == []
        assert result["orphan_pages"] == []

    def test_no_md_files(self, tmp_path):
        """wiki 中没有 .md 文件"""
        d = tmp_path / "empty"
        d.mkdir()
        (d / "readme.txt").write_text("hello", encoding="utf-8")
        linter = LintTool(str(d))
        result = linter.run_all()
        assert result["health_score"] == 100
        assert result["broken_links"] == []

    def test_all_nav_files_only(self, tmp_path):
        """只有导航文件时"""
        d = tmp_path / "nav_only"
        d.mkdir()
        (d / "index.md").write_text("# Index\n\n", encoding="utf-8")
        (d / "overview.md").write_text("# Overview\n\n", encoding="utf-8")
        (d / "log.md").write_text("# Log\n\n", encoding="utf-8")
        linter = LintTool(str(d))
        orphans = linter.check_orphan_pages()
        assert "index.md" not in orphans
        assert "overview.md" not in orphans
        assert "log.md" not in orphans
