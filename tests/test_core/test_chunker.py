"""
Chunker 单元测试 — heading-based Markdown 切分
"""
import re

import pytest

from src.core.search.chunker import (
    CHUNK_MAX_SIZE,
    CHUNK_MIN_SIZE,
    CHUNK_TARGET_SIZE,
    Section,
    chunk_page,
    _make_chunk_id,
    _parse_headings,
    _merge_chunks,
    _split_oversized,
)


# ============================================================================
# _parse_headings
# ============================================================================


class TestParseHeadings:
    def test_empty_content(self):
        sections = _parse_headings("")
        assert len(sections) == 1
        assert sections[0].heading == ""

    def test_no_headings(self):
        sections = _parse_headings("纯文本段落。\n没有标题。")
        assert len(sections) == 1
        assert sections[0].heading == ""

    def test_single_h2(self):
        sections = _parse_headings("## 概述\n\n内容内容。\n")
        assert len(sections) == 1
        assert sections[0].heading == "概述"
        assert sections[0].level == 2
        assert sections[0].breadcrumb == []

    def test_multiple_h2(self):
        md = "## A\n\na内容\n\n## B\n\nb内容\n"
        sections = _parse_headings(md)
        assert len(sections) == 2
        assert sections[0].heading == "A"
        assert sections[1].heading == "B"

    def test_nested_headings(self):
        """### 子标题应该在 breadcrumb 中携带父标题"""
        md = "## 父\n\n### 子\n\n子内容\n"
        sections = _parse_headings(md)
        assert len(sections) == 2
        assert sections[0].heading == "父"
        assert sections[0].level == 2
        assert sections[1].heading == "子"
        assert sections[1].level == 3
        assert sections[1].breadcrumb == ["父"]

    def test_deep_nesting(self):
        md = "## L1\n\n### L2\n\n#### L3\n\nL3内容\n"
        sections = _parse_headings(md)
        assert len(sections) == 3
        assert sections[0].heading == "L1"
        assert sections[1].heading == "L2"
        assert sections[1].breadcrumb == ["L1"]
        assert sections[2].heading == "L3"
        assert sections[2].breadcrumb == ["L1", "L2"]

    def test_heading_level_mismatch(self):
        """## → ####（跳级）应该正确弹栈"""
        md = "## A\n\n#### B\n\nB内容\n"
        sections = _parse_headings(md)
        assert len(sections) == 2
        assert sections[0].heading == "A"
        assert sections[1].heading == "B"
        assert sections[1].level == 4

    def test_h1_not_parsed(self):
        """H1 (#) 不应被匹配，应作为普通内容"""
        md = "# 总标题\n\n## 子章节\n\n内容。\n"
        sections = _parse_headings(md)
        assert len(sections) == 2  # 第一个是 H1 之前的空 section + H1 内容
        assert sections[0].heading == ""  # H1 内容是普通内容
        assert sections[1].heading == "子章节"


# ============================================================================
# chunk_page
# ============================================================================


class TestChunkPage:
    def test_empty_page(self):
        chunks = chunk_page("empty.md", "")
        assert len(chunks) == 0

    def test_simple_page(self):
        md = "## 配置\n\nAPP_NAME=WikiApp\nPORT=8766\n"
        chunks = chunk_page("config.md", md)
        assert len(chunks) >= 1
        assert all(c.path == "config.md" for c in chunks)
        assert all(c.heading == "配置" for c in chunks)

    def test_multiple_sections(self):
        md = (
            "## A\n\n" + "a" * 300 + "\n\n"
            "## B\n\n" + "b" * 300 + "\n\n"
            "## C\n\n" + "c" * 300 + "\n"
        )
        chunks = chunk_page("multi.md", md)
        # Each section is 300+ chars, so 3+ chunks
        assert len(chunks) >= 3

    def test_nested_breadcrumb(self):
        md = (
            "## 数据库\n\n"
            "### 关系型\n\n" + "关系型数据库介绍。" * 20 + "\n\n"
            "### 非关系型\n\n" + "NoSQL 介绍。" * 20 + "\n"
        )
        chunks = chunk_page("db.md", md)
        for c in chunks:
            if c.heading in ("关系型", "非关系型"):
                assert c.breadcrumb == ["数据库"], f"breadcrumb={c.breadcrumb}"

    def test_oversized_section(self):
        """超大章节应被切分为多个 chunk"""
        big = "## 大章节\n\n" + "段落内容。" * 500
        chunks = chunk_page("big.md", big)
        assert len(chunks) > 1
        assert all(c.heading == "大章节" for c in chunks)

    def test_chunk_size_within_target(self):
        """普通大小的 chunk 不应被切分"""
        md = "## 普通\n\n" + "内容。" * 100  # ~300 chars
        chunks = chunk_page("normal.md", md)
        assert len(chunks) == 1
        assert len(chunks[0].content) < CHUNK_MAX_SIZE * 1.5

    def test_chunk_id_stable(self):
        """相同内容的 chunk ID 应一致"""
        md = "## 测试\n\n稳定内容。"
        a = chunk_page("test.md", md)
        b = chunk_page("test.md", md)
        assert a[0].id == b[0].id

    def test_metadata_structure(self):
        """每个 chunk 应包含完整 metadata"""
        md = "## 标题\n\n正文内容\n"
        chunks = chunk_page("entities/test.md", md)
        c = chunks[0]
        meta = c.to_metadata()
        assert meta["path"] == "entities/test.md"
        assert meta["heading"] == "标题"
        assert meta["level"] == 2
        assert isinstance(meta["breadcrumb"], str)
        assert isinstance(meta["start_line"], int)
        assert isinstance(meta["end_line"], int)
        assert isinstance(meta["chunk_index"], int)
        assert isinstance(meta["total_chunks"], int)
        assert meta["page_hash"] != ""

    def test_overlap_content(self):
        """超大 chunk 的相邻 chunk 应有重叠字符"""
        huge = "## 大章\n\n" + "内容段落。" * 600 + "\n\n" + "新的段落内容。" * 200
        chunks = chunk_page("overlap.md", huge)
        if len(chunks) > 1:
            # 相邻 chunk 应有内容重叠
            overlap = _find_overlap(chunks[0].content, chunks[1].content)
            assert overlap > 0

    def test_real_wiki_page(self):
        """模拟真实 Wiki 页面"""
        md = """# LangGraph

## 概述

LangGraph 是一个构建有状态、多参与者 LLM 应用的状态图框架。
它扩展了 LangChain，提供对图执行周期的精细控制。

## 核心概念

### StateGraph

StateGraph 是 LangGraph 的核心类，代表一个有向图。
每个节点代表一个处理步骤，边代表执行流程。

### Checkpointer

Checkpointer 负责在每个 super-step 保存 State 快照。
支持 MemorySaver、SqliteSaver、PostgresSaver。

## 多 Agent 架构

2026 年推荐 Subagents as Tools 模式。
"""
        chunks = chunk_page("langgraph.md", md)
        assert len(chunks) >= 3
        # 检查 breadcrumb
        for c in chunks:
            if c.heading in ("StateGraph", "Checkpointer"):
                assert "核心概念" in c.breadcrumb


# ============================================================================
# 合并与切分
# ============================================================================


class TestMergeAndSplit:
    def test_merge_small_chunks_same_parent(self):
        """同父级过小的 chunk 应合并"""
        from src.core.search.chunker import Chunk, _adjust_chunks

        c1 = Chunk(
            id="a", path="p.md", content="短内容。",
            heading="A", level=2, breadcrumb=[],
            start_line=1, end_line=2, page_hash="h1",
        )
        c2 = Chunk(
            id="b", path="p.md", content="也短。",
            heading="B", level=2, breadcrumb=[],
            start_line=3, end_line=4, page_hash="h1",
        )
        result = _adjust_chunks([c1, c2], "p.md", "h1",
                                CHUNK_TARGET_SIZE, CHUNK_MAX_SIZE, CHUNK_MIN_SIZE, 0)
        # 应该合并为一个
        assert len(result) == 1

    def test_not_merge_different_breadcrumb(self):
        """不同父级即使过小也不应合并"""
        from src.core.search.chunker import Chunk, _adjust_chunks

        c1 = Chunk(
            id="a", path="p.md", content="短内容。",
            heading="A1", level=3, breadcrumb=["父A"],
            start_line=1, end_line=2, page_hash="h1",
        )
        c2 = Chunk(
            id="b", path="p.md", content="也短。",
            heading="B1", level=3, breadcrumb=["父B"],
            start_line=3, end_line=4, page_hash="h1",
        )
        result = _adjust_chunks([c1, c2], "p.md", "h1",
                                CHUNK_TARGET_SIZE, CHUNK_MAX_SIZE, CHUNK_MIN_SIZE, 0)
        # 不同 parent，不应合并
        assert len(result) == 2


# ============================================================================
# 边缘情况
# ============================================================================


class TestEdgeCases:
    def test_only_headings_no_content(self):
        """只有标题没有内容的页面"""
        md = "## A\n## B\n## C\n"
        chunks = chunk_page("empty-sections.md", md)
        assert len(chunks) == 0  # 无实质性内容

    def test_code_block_preserved(self):
        """代码块不应被切分破坏"""
        md = "## 代码\n\n```python\nprint('hello')\n```\n\n## 说明\n\n代码如上。\n"
        chunks = chunk_page("code.md", md)
        assert len(chunks) >= 1

    def test_heading_with_special_chars(self):
        """标题含特殊字符"""
        md = "## C++ 性能优化（2026）\n\n内容。\n### 多线程 & 异步\n\n更多。\n"
        chunks = chunk_page("special.md", md)
        assert any("C++" in c.heading for c in chunks)

    def test_very_long_heading(self):
        """超长标题应保留"""
        long_title = "非常长的标题" * 30
        md = f"## {long_title}\n\n内容。\n"
        chunks = chunk_page("long-heading.md", md)
        assert len(chunks) == 1
        assert long_title in chunks[0].content

    def test_mixed_cjk_and_english(self):
        """中英文混合"""
        md = "## Python async/await 异步编程\n\n协程 coroutine 是核心概念。\n### event_loop 事件循环\n\n负责调度。\n"
        chunks = chunk_page("mixed.md", md)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.path == "mixed.md"


# ============================================================================
# 辅助函数
# ============================================================================


def _find_overlap(a: str, b: str) -> int:
    """计算两个字符串的重叠公共子串长度（近似）"""
    # 简单方法：取 a 的后 200 字符和 b 的前 200 字符的公共部分
    tail = a[-200:]
    head = b[:200]
    # 从长到短找公共子串
    for length in range(min(len(tail), len(head)), 0, -1):
        for start in range(len(tail) - length + 1):
            sub = tail[start:start + length]
            if head.startswith(sub):
                return length
    return 0
