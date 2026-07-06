"""
WriteTool 单元测试
"""
import os

import pytest

from src.core.validator import ValidatorError
from src.tools.write_tool import WriteTool

# 含完整 frontmatter 的有效内容
VALID_CONTENT = """---
title: "测试页面"
type: concept
tags: [test]
---
# 测试页面

这是一个内容。参见 [[entities/other.md]]。
"""


@pytest.fixture
def wiki_dir(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    return wiki


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------


def test_write_page_creates_file(wiki_dir):
    """写入文件，内容正确"""
    tool = WriteTool(base_dir=str(wiki_dir))
    result = tool.write_page("entities/new_page.md", VALID_CONTENT)

    # normpath 在 Windows 上会把 / 变成 \\, 统一用正斜杠比较
    result = result.replace("\\", "/")
    assert result == "entities/new_page.md"
    assert (wiki_dir / "entities" / "new_page.md").exists()
    assert "测试页面" in (wiki_dir / "entities" / "new_page.md").read_text(encoding="utf-8")


def test_write_page_returns_relative_path(wiki_dir):
    """返回值是被规范化的相对路径"""
    tool = WriteTool(base_dir=str(wiki_dir))
    result = tool.write_page("concepts/page.md", VALID_CONTENT)
    assert os.path.normpath(result) == result


def test_write_page_overwrite(wiki_dir):
    """覆写已存在的文件"""
    tool = WriteTool(base_dir=str(wiki_dir))
    tool.write_page("entities/existing.md", VALID_CONTENT)

    updated = VALID_CONTENT.replace("测试页面", "已更新")
    tool.write_page("entities/existing.md", updated)
    content = (wiki_dir / "entities" / "existing.md").read_text(encoding="utf-8")
    assert "已更新" in content


# ---------------------------------------------------------------------------
# 边界条件
# ---------------------------------------------------------------------------


def test_write_page_creates_intermediate_dirs(wiki_dir):
    """自动创建中间目录"""
    tool = WriteTool(base_dir=str(wiki_dir))
    tool.write_page("concepts/a/b/c/page.md", VALID_CONTENT)
    assert (wiki_dir / "concepts" / "a" / "b" / "c" / "page.md").exists()


def test_write_page_empty_content(wiki_dir):
    """空内容写入（不含 frontmatter 因此需跳过校验）"""
    tool = WriteTool(base_dir=str(wiki_dir))
    tool.write_page("empty_page.md", "", validate=False)
    assert (wiki_dir / "empty_page.md").read_text(encoding="utf-8") == ""


def test_write_page_validate_false_skips_check(wiki_dir):
    """validate=False 跳过校验"""
    tool = WriteTool(base_dir=str(wiki_dir))
    tool.write_page("entities/test.md", "不含 frontmatter 的内容", validate=False)
    assert (wiki_dir / "entities" / "test.md").exists()


def test_write_page_skip_validation(wiki_dir):
    """validate=False 可以写入无 frontmatter 的内容"""
    tool = WriteTool(base_dir=str(wiki_dir))
    tool.write_page("entities/minimal.md", "# 只有标题", validate=False)
    assert (wiki_dir / "entities" / "minimal.md").exists()


# ---------------------------------------------------------------------------
# 错误路径 — 路径权限
# ---------------------------------------------------------------------------


def test_write_page_outside_wiki(wiki_dir):
    tool = WriteTool(base_dir=str(wiki_dir))
    with pytest.raises(PermissionError):
        tool.write_page("../outside.md", VALID_CONTENT, validate=False)


def test_write_page_absolute_path(wiki_dir):
    tool = WriteTool(base_dir=str(wiki_dir))
    with pytest.raises(PermissionError):
        tool.write_page("/etc/hosts", VALID_CONTENT, validate=False)


def test_write_page_traversal_nested(wiki_dir):
    tool = WriteTool(base_dir=str(wiki_dir))
    with pytest.raises(PermissionError):
        tool.write_page("concepts/../../outside.md", VALID_CONTENT, validate=False)


# ---------------------------------------------------------------------------
# 错误路径 — 内容校验
# ---------------------------------------------------------------------------


def test_write_page_validation_rejects_no_frontmatter(wiki_dir):
    """无 frontmatter 的内容被拒绝"""
    tool = WriteTool(base_dir=str(wiki_dir))
    with pytest.raises(ValidatorError, match="Missing YAML frontmatter"):
        tool.write_page("entities/bad.md", "# 只有标题")


def test_write_page_validation_rejects_no_type(wiki_dir):
    """frontmatter 缺少 type"""
    content = """---
title: "test"
---
# Test
[[other.md]]
"""
    tool = WriteTool(base_dir=str(wiki_dir))
    with pytest.raises(ValidatorError, match="type"):
        tool.write_page("entities/test.md", content)


def test_write_page_validation_rejects_no_title(wiki_dir):
    """frontmatter 缺少 title"""
    content = """---
type: concept
---
# Test
[[other.md]]
"""
    tool = WriteTool(base_dir=str(wiki_dir))
    with pytest.raises(ValidatorError, match="title"):
        tool.write_page("entities/test.md", content)


def test_write_page_validation_rejects_script_tag(wiki_dir):
    """包含 <script> 的内容被拒绝"""
    content = VALID_CONTENT.replace("[[entities/other.md]]", "<script>alert(1)</script>")
    tool = WriteTool(base_dir=str(wiki_dir))
    with pytest.raises(ValidatorError, match="forbidden"):
        tool.write_page("entities/test.md", content)


def test_write_page_validation_rejects_no_wikilink(wiki_dir):
    """没有 [[wikilink]] 的内容被拒绝"""
    content = """---
title: "孤立页"
type: concept
tags: []
---
# 孤立页

没有链接的页面。
"""
    tool = WriteTool(base_dir=str(wiki_dir))
    with pytest.raises(ValidatorError, match="wikilink"):
        tool.write_page("concepts/test.md", content)
