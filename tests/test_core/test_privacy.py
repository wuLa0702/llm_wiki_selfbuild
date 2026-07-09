"""
PrivacyManager + 隐私标记单元测试
"""
import pytest

from src.core.privacy import PrivacyManager

VALID_CONTENT = """---
title: "测试"
type: entity
tags: []
---
# 测试

文本内容 [[entities/other.md]]。
"""


@pytest.fixture
def pm(tmp_path):
    """基于临时数据库的 PrivacyManager"""
    return PrivacyManager(db_path=str(tmp_path / "test.db"))


class TestPrivacyManager:
    def test_default_rules_loaded(self, pm):
        """初始化后默认规则已加载"""
        rules = pm.list_rules()
        assert len(rules) > 10
        # 检查常见关键词
        keywords = [r["keyword"] for r in rules]
        assert "恋爱" in keywords
        assert "银行卡" in keywords
        assert "身份证" in keywords
        assert "病历" in keywords

    def test_add_custom_rule(self, pm):
        """添加用户自定义规则"""
        pm.add_rule("自定义敏感词", "general")
        rules = pm.list_rules()
        custom = [r for r in rules if r["keyword"] == "自定义敏感词"]
        assert len(custom) == 1
        assert custom[0]["is_default"] == 0

    def test_remove_custom_rule(self, pm):
        """删除用户自定义规则"""
        pm.add_rule("temp_keyword", "general")
        pm.remove_rule("temp_keyword")
        keywords = [r["keyword"] for r in pm.list_rules()]
        assert "temp_keyword" not in keywords

    def test_match_hit(self, pm):
        """内容包含敏感词时返回匹配结果"""
        content = "我最近和女朋友分手了，心情很抑郁。"
        matches = pm.match(content)
        assert len(matches) >= 2
        matched_keywords = [m["keyword"] for m in matches]
        assert "分手" in matched_keywords
        assert "抑郁" in matched_keywords

    def test_match_miss(self, pm):
        """内容不含敏感词时返回空列表"""
        content = "今天天气真好，去公园散步。"
        matches = pm.match(content)
        assert matches == []

    def test_match_multiple_categories(self, pm):
        """命中多个分类的敏感词"""
        content = "我的银行卡密码是123456，身份证号是110101..."
        matches = pm.match(content)
        categories = set(m["category"] for m in matches)
        assert "financial" in categories
        assert "identity" in categories


class TestPrivacyInject:
    """测试 frontmatter 隐私标记注入"""

    def test_inject_privacy(self):
        from src.core.compiler import WikiCompiler

        content = VALID_CONTENT
        matches = [{"keyword": "恋爱", "category": "emotion"}]
        result = WikiCompiler._inject_privacy_frontmatter(content, matches)

        assert "visibility: restricted" in result
        assert "emotion" in result

    def test_inject_empty_matches(self):
        from src.core.compiler import WikiCompiler

        result = WikiCompiler._inject_privacy_frontmatter(VALID_CONTENT, [])
        assert result == VALID_CONTENT

    def test_inject_no_frontmatter(self):
        from src.core.compiler import WikiCompiler

        content = "没有 frontmatter 的内容"
        matches = [{"keyword": "恋爱", "category": "emotion"}]
        result = WikiCompiler._inject_privacy_frontmatter(content, matches)
        assert result == content  # 无 frontmatter 则不修改

    def test_inject_preserves_title(self):
        from src.core.compiler import WikiCompiler

        matches = [{"keyword": "抑郁", "category": "emotion"}, {"keyword": "银行卡", "category": "financial"}]
        result = WikiCompiler._inject_privacy_frontmatter(VALID_CONTENT, matches)
        assert 'title: "测试"' in result
        assert "visibility: restricted" in result
        assert "privacy_categories:" in result
        assert "emotion" in result
        assert "financial" in result


class TestPrivacyAPI:
    """隐私 API 端点测试"""

    def test_get_rules(self, client, mocker):
        """GET /v1/privacy/rules 返回规则列表"""
        mocker.patch("src.api.routes.misc.PrivacyManager")
        response = client.get("/v1/privacy/rules")
        assert response.status_code == 200
        assert "rules" in response.json()

    def test_add_rule(self, client, mocker):
        """POST /v1/privacy/rules 添加规则"""
        mock_pm = mocker.patch("src.api.routes.misc.PrivacyManager")
        response = client.post("/v1/privacy/rules", json={"keyword": "测试词", "category": "general"})
        assert response.status_code == 200
        mock_pm.return_value.add_rule.assert_called_once_with("测试词", "general")

    def test_add_rule_missing_keyword(self, client):
        """缺少 keyword 返回 400"""
        response = client.post("/v1/privacy/rules", json={"category": "general"})
        assert response.status_code == 400

    def test_delete_rule(self, client, mocker):
        """DELETE /v1/privacy/rules/{keyword} 删除规则"""
        mock_pm = mocker.patch("src.api.routes.misc.PrivacyManager")
        response = client.delete("/v1/privacy/rules/测试词")
        assert response.status_code == 200
        mock_pm.return_value.remove_rule.assert_called_once_with("测试词")
