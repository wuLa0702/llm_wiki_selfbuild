"""
WriteTool 单元测试
"""
import os

import pytest

from src.tools.write_tool import WriteTool


@pytest.fixture
def wiki_dir(tmp_path):
    """创建一个模拟 wiki/ 目录"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "existing.md").write_text("old content", encoding="utf-8")
    return wiki


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------


def test_write_page_creates_file(wiki_dir):
    """写入文件，内容正确"""
    tool = WriteTool(base_dir=str(wiki_dir))
    result = tool.write_page("new_page.md", "# New Page")

    assert result == "new_page.md"
    assert (wiki_dir / "new_page.md").exists()
    assert (wiki_dir / "new_page.md").read_text(encoding="utf-8") == "# New Page"


def test_write_page_returns_relative_path(wiki_dir):
    """返回值是被规范化的相对路径"""
    tool = WriteTool(base_dir=str(wiki_dir))
    result = tool.write_page("subdir/page.md", "content")
    assert os.path.normpath(result) == result
    assert "subdir" in result


def test_write_page_overwrite(wiki_dir):
    """覆写已存在的文件"""
    tool = WriteTool(base_dir=str(wiki_dir))
    tool.write_page("existing.md", "new content")
    assert (wiki_dir / "existing.md").read_text(encoding="utf-8") == "new content"


# ---------------------------------------------------------------------------
# 边界条件
# ---------------------------------------------------------------------------


def test_write_page_creates_intermediate_dirs(wiki_dir):
    """自动创建中间目录"""
    tool = WriteTool(base_dir=str(wiki_dir))
    tool.write_page("a/b/c/page.md", "deep content")

    assert (wiki_dir / "a" / "b" / "c" / "page.md").exists()
    assert (wiki_dir / "a" / "b" / "c" / "page.md").read_text(encoding="utf-8") == "deep content"


def test_write_page_empty_content(wiki_dir):
    """写入空内容"""
    tool = WriteTool(base_dir=str(wiki_dir))
    tool.write_page("empty_page.md", "")
    assert (wiki_dir / "empty_page.md").read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------------------
# 错误路径
# ---------------------------------------------------------------------------


def test_write_page_outside_wiki(wiki_dir):
    """.. 穿越被拒绝"""
    tool = WriteTool(base_dir=str(wiki_dir))
    with pytest.raises(PermissionError):
        tool.write_page("../outside.md", "hack")


def test_write_page_absolute_path(wiki_dir):
    """绝对路径被拒绝"""
    tool = WriteTool(base_dir=str(wiki_dir))
    with pytest.raises(PermissionError):
        tool.write_page("/etc/hosts", "hack")


def test_write_page_traversal_nested(wiki_dir):
    """嵌套路径穿越被拒绝"""
    tool = WriteTool(base_dir=str(wiki_dir))
    with pytest.raises(PermissionError):
        tool.write_page("a/../../outside.md", "hack")
