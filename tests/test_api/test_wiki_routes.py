"""
Wiki 浏览路由测试
"""
import os

import pytest


@pytest.fixture
def wiki_content(tmp_path):
    """在 tmp_path 下创建模拟 wiki 目录，供浏览路由使用"""
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    entities = wiki / "entities"
    entities.mkdir()
    concepts = wiki / "concepts"
    concepts.mkdir()

    (entities / "python.md").write_text(
        "# Python\n\nPython 是一种编程语言。\n\n参见 [[concepts/ai.md|人工智能]]。",
        encoding="utf-8",
    )
    (concepts / "ai.md").write_text(
        "# 人工智能\n\nAI 是计算机科学分支。\n\n常用语言: [[entities/python.md]]",
        encoding="utf-8",
    )
    return str(wiki)


class TestWikiRoutes:
    """Wiki 浏览路由测试"""

    def setup_method(self):
        """每个测试前重置 monkeypatched 路径"""
        self._orig = None

    # ==================================================================
    # Wiki 首页
    # ==================================================================

    def test_wiki_index_returns_html(self, client, wiki_content, mocker):
        """GET /wiki 返回 HTML 页面"""
        mocker.patch("src.main.ReadTool.__init__", return_value=None)
        mocker.patch("src.main.WikiRepository.__init__", return_value=None)

        reader_mock = mocker.MagicMock()
        reader_mock.base_dir = wiki_content
        mocker.patch("src.main.ReadTool", return_value=reader_mock)

        repo_mock = mocker.MagicMock()
        repo_mock.get_page.return_value = {"page_type": "entity"}
        mocker.patch("src.main.WikiRepository", return_value=repo_mock)

        # 模拟 os.walk 返回 wiki 目录结构
        mocker.patch("os.walk", return_value=iter([
            (os.path.join(wiki_content, "entities"), [], ["python.md"]),
            (os.path.join(wiki_content, "concepts"), [], ["ai.md"]),
        ]))

        response = client.get("/wiki")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "<h1>LLM Wiki 知识库</h1>" in response.text
        assert "entities/python.md" in response.text
        assert "concepts/ai.md" in response.text

    # ==================================================================
    # Wiki 单页
    # ==================================================================

    def test_wiki_page_renders_content(self, client, wiki_content, mocker):
        """GET /wiki/entities/python.md 渲染页面内容"""
        mocker.patch("src.main.ReadTool.__init__", return_value=None)
        reader_mock = mocker.MagicMock()
        reader_mock.base_dir = wiki_content
        reader_mock.read_file.return_value = "# Python\n\n参见 [[concepts/ai.md]]。"
        mocker.patch("src.main.ReadTool", return_value=reader_mock)

        response = client.get("/wiki/entities/python.md")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Python" in response.text
        assert 'href="/wiki/concepts/ai.md"' in response.text  # 链接已转换

    def test_wiki_page_wikilink_with_display(self, client, wiki_content, mocker):
        """[[path|显示名]] 格式正确转换为链接"""
        mocker.patch("src.main.ReadTool.__init__", return_value=None)
        reader_mock = mocker.MagicMock()
        reader_mock.base_dir = wiki_content
        reader_mock.read_file.return_value = "参见 [[concepts/ai.md|人工智能]]。"
        mocker.patch("src.main.ReadTool", return_value=reader_mock)

        response = client.get("/wiki/entities/python.md")
        assert response.status_code == 200
        assert 'href="/wiki/concepts/ai.md"' in response.text
        assert "人工智能" in response.text

    def test_wiki_page_404(self, client, wiki_content, mocker):
        """不存在的页面返回 404"""
        mocker.patch("src.main.ReadTool.__init__", return_value=None)
        reader_mock = mocker.MagicMock()
        reader_mock.read_file.side_effect = FileNotFoundError
        mocker.patch("src.main.ReadTool", return_value=reader_mock)

        response = client.get("/wiki/nonexistent.md")
        assert response.status_code == 404

    def test_wiki_page_permission_error(self, client, wiki_content, mocker):
        """ReadTool 抛 PermissionError 时返回 403"""
        mocker.patch("src.main.ReadTool.__init__", return_value=None)
        reader_mock = mocker.MagicMock()
        reader_mock.read_file.side_effect = PermissionError("Access denied")
        mocker.patch("src.main.ReadTool", return_value=reader_mock)

        response = client.get("/wiki/outside.md")
        assert response.status_code == 403

    # ==================================================================
    # convert_wikilinks 单元测试
    # ==================================================================

    def test_convert_wikilinks_simple(self):
        """[[path]] → <a href=...>"""
        from src.main import _convert_wikilinks

        result = _convert_wikilinks("参见 [[concepts/ai.md]]。")
        assert '<a href="/wiki/concepts/ai.md"' in result
        assert ">concepts/ai.md</a>" in result

    def test_convert_wikilinks_with_display(self):
        """[[path|显示名]] → <a href=...>显示名</a>"""
        from src.main import _convert_wikilinks

        result = _convert_wikilinks("参见 [[concepts/ai.md|人工智能]]。")
        assert 'href="/wiki/concepts/ai.md"' in result
        assert ">人工智能</a>" in result

    def test_convert_wikilinks_multiple(self):
        """多个链接都被转换"""
        from src.main import _convert_wikilinks

        result = _convert_wikilinks("[[a.md]] 和 [[b.md|B]] 和 [[c.md]]")
        assert result.count('<a href="/wiki/') == 3
