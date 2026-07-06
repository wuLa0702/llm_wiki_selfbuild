"""
WikiValidator 单元测试
"""
import pytest

from src.core.validator import ValidatorError, WikiValidator

# 有效内容示例
VALID_CONTENT = """---
title: "Python"
type: entity
tags: [编程语言, AI]
---
# Python

Python 是一种编程语言。用于 [[concepts/ai.md|人工智能]]。
"""


class TestValidatePath:
    def test_valid_path(self):
        """合法路径不抛异常"""
        WikiValidator.validate_path("entities/python.md")
        WikiValidator.validate_path("concepts/ai.md")
        WikiValidator.validate_path("sources/book.md")

    def test_path_empty(self):
        with pytest.raises(ValidatorError, match="empty"):
            WikiValidator.validate_path("")

    def test_path_dot_dot(self):
        with pytest.raises(ValidatorError, match=".."):
            WikiValidator.validate_path("entities/../outside.md")

    def test_path_wrong_prefix(self):
        with pytest.raises(ValidatorError):
            WikiValidator.validate_path("raw/sources/test.md")

    def test_path_no_md_extension(self):
        with pytest.raises(ValidatorError, match=".md"):
            WikiValidator.validate_path("entities/python")


class TestValidateFrontmatter:
    def test_valid_frontmatter(self):
        """有效 frontmatter 返回解析结果"""
        fm = WikiValidator.validate_frontmatter(VALID_CONTENT)
        assert fm["title"] == "Python"
        assert fm["type"] == "entity"
        assert "编程语言" in fm["tags"]

    def test_missing_frontmatter(self):
        with pytest.raises(ValidatorError, match="Missing YAML frontmatter"):
            WikiValidator.validate_frontmatter("# 没有 frontmatter")

    def test_missing_title(self):
        content = """---
type: entity
---
# Test
"""
        with pytest.raises(ValidatorError, match="title"):
            WikiValidator.validate_frontmatter(content)

    def test_missing_type(self):
        content = """---
title: "test"
---
# Test
"""
        with pytest.raises(ValidatorError, match="type"):
            WikiValidator.validate_frontmatter(content)

    def test_invalid_type(self):
        content = """---
title: "test"
type: invalid_type
---
# Test
"""
        with pytest.raises(ValidatorError, match="Invalid type"):
            WikiValidator.validate_frontmatter(content)


class TestValidateNoExecutable:
    def test_clean_content(self):
        """正常内容不抛异常"""
        WikiValidator.validate_no_executable(VALID_CONTENT)

    def test_script_tag(self):
        with pytest.raises(ValidatorError, match="forbidden"):
            WikiValidator.validate_no_executable("<script>alert(1)</script>")

    def test_iframe_tag(self):
        with pytest.raises(ValidatorError):
            WikiValidator.validate_no_executable("<iframe src='http://evil.com'></iframe>")

    def test_javascript_link(self):
        with pytest.raises(ValidatorError):
            WikiValidator.validate_no_executable('<a href="javascript:alert(1)">click</a>')


class TestValidateWikilinks:
    def test_has_wikilinks(self):
        links = WikiValidator.validate_wikilinks(VALID_CONTENT)
        assert "concepts/ai.md" in links

    def test_no_wikilinks(self):
        content = """---
title: "孤岛"
type: concept
---
# 孤岛
没有链接的页面。
"""
        with pytest.raises(ValidatorError, match="wikilink"):
            WikiValidator.validate_wikilinks(content)


class TestValidateAll:
    def test_valid_page(self):
        fm = WikiValidator.validate_all("entities/python.md", VALID_CONTENT)
        assert fm["title"] == "Python"
        assert fm["type"] == "entity"

    def test_invalid_path_propagates(self):
        with pytest.raises(ValidatorError, match=".."):
            WikiValidator.validate_all("../outside.md", VALID_CONTENT)

    def test_no_executable_propagates(self):
        bad = VALID_CONTENT.replace("[[concepts/ai.md|人工智能]]", "<script>x</script>")
        with pytest.raises(ValidatorError, match="forbidden"):
            WikiValidator.validate_all("entities/python.md", bad)
