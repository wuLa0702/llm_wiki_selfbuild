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
        mocker.patch("src.api.routes.wiki.ReadTool.__init__", return_value=None)
        mocker.patch("src.api.routes.wiki.WikiRepository.__init__", return_value=None)

        reader_mock = mocker.MagicMock()
        reader_mock.base_dir = wiki_content
        mocker.patch("src.api.routes.wiki.ReadTool", return_value=reader_mock)

        repo_mock = mocker.MagicMock()
        repo_mock.get_page.return_value = {"page_type": "entity"}
        mocker.patch("src.api.routes.wiki.WikiRepository", return_value=repo_mock)

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
        mocker.patch("src.api.routes.wiki.ReadTool.__init__", return_value=None)
        reader_mock = mocker.MagicMock()
        reader_mock.base_dir = wiki_content
        reader_mock.read_file.return_value = "# Python\n\n参见 [[concepts/ai.md]]。"
        mocker.patch("src.api.routes.wiki.ReadTool", return_value=reader_mock)

        response = client.get("/wiki/entities/python.md")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Python" in response.text
        assert 'href="/wiki/concepts/ai.md"' in response.text

    def test_wiki_page_wikilink_with_display(self, client, wiki_content, mocker):
        """[[path|显示名]] 格式正确转换为链接"""
        mocker.patch("src.api.routes.wiki.ReadTool.__init__", return_value=None)
        reader_mock = mocker.MagicMock()
        reader_mock.base_dir = wiki_content
        reader_mock.read_file.return_value = "参见 [[concepts/ai.md|人工智能]]。"
        mocker.patch("src.api.routes.wiki.ReadTool", return_value=reader_mock)

        response = client.get("/wiki/entities/python.md")
        assert response.status_code == 200
        assert 'href="/wiki/concepts/ai.md"' in response.text
        assert "人工智能" in response.text

    def test_wiki_page_404(self, client, wiki_content, mocker):
        """不存在的页面返回 404"""
        mocker.patch("src.api.routes.wiki.ReadTool.__init__", return_value=None)
        reader_mock = mocker.MagicMock()
        reader_mock.read_file.side_effect = FileNotFoundError
        mocker.patch("src.api.routes.wiki.ReadTool", return_value=reader_mock)

        response = client.get("/wiki/nonexistent.md")
        assert response.status_code == 404

    def test_wiki_page_permission_error(self, client, wiki_content, mocker):
        """ReadTool 抛 PermissionError 时返回 403"""
        mocker.patch("src.api.routes.wiki.ReadTool.__init__", return_value=None)
        reader_mock = mocker.MagicMock()
        reader_mock.read_file.side_effect = PermissionError("Access denied")
        mocker.patch("src.api.routes.wiki.ReadTool", return_value=reader_mock)

        response = client.get("/wiki/outside.md")
        assert response.status_code == 403

    # ==================================================================
    # convert_wikilinks 单元测试
    # ==================================================================

    def test_convert_wikilinks_simple(self):
        """[[path]] → <a href=...>"""
        from src.api.helpers import _convert_wikilinks

        result = _convert_wikilinks("参见 [[concepts/ai.md]]。")
        assert '<a href="/wiki/concepts/ai.md"' in result
        assert ">concepts/ai.md</a>" in result

    def test_convert_wikilinks_with_display(self):
        """[[path|显示名]] → <a href=...>显示名</a>"""
        from src.api.helpers import _convert_wikilinks

        result = _convert_wikilinks("参见 [[concepts/ai.md|人工智能]]。")
        assert 'href="/wiki/concepts/ai.md"' in result
        assert ">人工智能</a>" in result

    def test_convert_wikilinks_multiple(self):
        """多个链接都被转换"""
        from src.api.helpers import _convert_wikilinks

        result = _convert_wikilinks("[[a.md]] 和 [[b.md|B]] 和 [[c.md]]")
        assert result.count('<a href="/wiki/') == 3


class TestQueryViz:
    """GET /wiki/query 查询界面页面"""

    def test_query_viz_returns_html(self, client):
        """/wiki/query 返回 HTML 页面"""
        response = client.get("/wiki/query")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "知识问答" in response.text
        assert "/v1/query" in response.text
        assert "queryInput" in response.text


class TestGraphViz:
    """GET /wiki/graph 图谱可视化页面"""

    def test_graph_viz_returns_html(self, client, mocker):
        """/wiki/graph 返回 HTML 页面"""
        mocker.patch("src.core.graph.WikiGraph.to_dict", return_value={
            "nodes": [{"id": "a.md", "degree": {"in": 1, "out": 0}}],
            "edges": [{"source": "b.md", "target": "a.md"}],
            "stats": {"total_nodes": 1, "total_edges": 1, "avg_degree": 1.0},
        })

        response = client.get("/wiki/graph")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "vis-network" in response.text
        assert "/v1/graph" in response.text


class TestPagesApi:
    """GET /v1/pages JSON API 测试"""

    def test_list_pages_returns_json(self, client, wiki_content, mocker):
        """/v1/pages 返回 JSON 页面列表"""
        mocker.patch("src.api.routes.pages.WikiRepository.__init__", return_value=None)
        mocker.patch("src.api.routes.pages.ReadTool.__init__", return_value=None)

        reader_mock = mocker.MagicMock()
        reader_mock.base_dir = wiki_content
        reader_mock.read_file.return_value = "# Python\n"
        mocker.patch("src.api.routes.pages.ReadTool", return_value=reader_mock)

        repo_mock = mocker.MagicMock()
        repo_mock.get_page.return_value = {
            "path": "entities/python.md",
            "title": "Python",
            "page_type": "entity",
            "tags": ["lang"],
            "word_count": 10,
            "updated_at": "2026-07-07T10:00:00",
            "links": ["concepts/ai.md"],
            "backlinks": ["index.md"],
        }
        mocker.patch("src.api.routes.pages.WikiRepository", return_value=repo_mock)

        response = client.get("/v1/pages")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "pages" in data
        assert data["pages"][0]["path"] == "entities/python.md"
        assert data["pages"][0]["links_count"] == 1
        assert data["pages"][0]["backlinks_count"] == 1

    def test_list_pages_filter_by_type(self, client, wiki_content, mocker):
        """/v1/pages?type=entity 只返回实体"""
        mocker.patch("src.api.routes.pages.WikiRepository.__init__", return_value=None)
        mocker.patch("src.api.routes.pages.ReadTool.__init__", return_value=None)

        reader_mock = mocker.MagicMock()
        reader_mock.base_dir = wiki_content
        mocker.patch("src.api.routes.pages.ReadTool", return_value=reader_mock)

        repo_mock = mocker.MagicMock()
        repo_mock.get_page.side_effect = [
            {"path": "entities/python.md", "title": "Python", "page_type": "entity",
             "tags": [], "word_count": 10, "updated_at": "", "links": [], "backlinks": []},
            None,
        ]
        mocker.patch("src.api.routes.pages.WikiRepository", return_value=repo_mock)

        response = client.get("/v1/pages?type=entity")
        assert response.status_code == 200
        data = response.json()
        assert all(p["page_type"] == "entity" for p in data["pages"])

    def test_page_detail_returns_content(self, client, wiki_content, mocker):
        """/v1/pages/xxx.md 返回完整内容"""
        mocker.patch("src.api.routes.pages.WikiRepository.__init__", return_value=None)
        mocker.patch("src.api.helpers.WikiRepository.__init__", return_value=None)
        mocker.patch("src.api.routes.pages.ReadTool.__init__", return_value=None)

        reader_mock = mocker.MagicMock()
        reader_mock.base_dir = wiki_content
        reader_mock.read_file.return_value = "# Python\n\nPython is a language."
        mocker.patch("src.api.routes.pages.ReadTool", return_value=reader_mock)

        repo_mock = mocker.MagicMock()
        repo_mock.get_page.return_value = {
            "path": "entities/python.md",
            "title": "Python",
            "page_type": "entity",
            "tags": ["lang"],
            "links": ["concepts/ai.md"],
            "backlinks": ["index.md"],
            "visibility": "public",
            "created_at": "2026-07-06T10:00:00",
            "updated_at": "2026-07-07T10:00:00",
        }
        mocker.patch("src.api.routes.pages.WikiRepository", return_value=repo_mock)
        mocker.patch("src.api.helpers.WikiRepository", return_value=repo_mock)

        response = client.get("/v1/pages/entities/python.md")
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Python"
        assert "Python is a language" in data["content"]
        assert "concepts/ai.md" in data["links"]
        assert "index.md" in data["backlinks"]

    def test_page_detail_404(self, client, mocker):
        """不存在的页面返回 404"""
        mocker.patch("src.api.routes.pages.WikiRepository.__init__", return_value=None)
        repo_mock = mocker.MagicMock()
        repo_mock.get_page.return_value = None
        mocker.patch("src.api.routes.pages.WikiRepository", return_value=repo_mock)

        response = client.get("/v1/pages/nonexistent.md")
        assert response.status_code == 404

    def test_page_detail_permission_denied(self, client, wiki_content, mocker):
        """restricted 页面返回 403 locked"""
        mocker.patch("src.api.routes.pages.WikiRepository.__init__", return_value=None)
        mocker.patch("src.api.helpers.WikiRepository.__init__", return_value=None)
        mocker.patch("src.api.routes.pages.ReadTool.__init__", return_value=None)

        reader_mock = mocker.MagicMock()
        reader_mock.base_dir = wiki_content
        mocker.patch("src.api.routes.pages.ReadTool", return_value=reader_mock)

        repo_mock = mocker.MagicMock()
        repo_mock.get_page.return_value = {
            "path": "entities/secret.md",
            "title": "Secret",
            "page_type": "entity",
            "visibility": "restricted",
        }
        mocker.patch("src.api.routes.pages.WikiRepository", return_value=repo_mock)
        mocker.patch("src.api.helpers.WikiRepository", return_value=repo_mock)

        response = client.get("/v1/pages/entities/secret.md")
        assert response.status_code == 403
        data = response.json()
        assert data["status"] == "locked"


class TestUsageApi:
    """GET /v1/usage 端点测试"""

    def test_usage_today(self, client, mocker):
        """/v1/usage 返回今日 token 统计"""
        mocker.patch("src.api.routes.misc.TokenTracker.__init__", return_value=None)
        tracker_mock = mocker.MagicMock()
        tracker_mock.today_summary.return_value = {
            "period": "today",
            "total_tokens": 1500,
            "total_cost_estimate": "¥0.003",
            "by_operation": [{"operation": "chat", "tokens": 1500, "cost_estimate": "¥0.003"}],
        }
        mocker.patch("src.api.routes.misc.TokenTracker", return_value=tracker_mock)

        response = client.get("/v1/usage")
        assert response.status_code == 200
        data = response.json()
        assert data["period"] == "today"
        assert data["total_tokens"] == 1500

    def test_usage_weekly(self, client, mocker):
        """/v1/usage?period=week 返回本周统计"""
        mocker.patch("src.api.routes.misc.TokenTracker.__init__", return_value=None)
        tracker_mock = mocker.MagicMock()
        tracker_mock.weekly_summary.return_value = {
            "period": "week",
            "total_tokens": 10000,
            "total_cost_estimate": "¥0.02",
            "by_operation": [],
        }
        mocker.patch("src.api.routes.misc.TokenTracker", return_value=tracker_mock)

        response = client.get("/v1/usage?period=week")
        assert response.status_code == 200
        assert response.json()["period"] == "week"

    def test_usage_monthly(self, client, mocker):
        """/v1/usage?period=month 返回月统计"""
        mocker.patch("src.api.routes.misc.TokenTracker.__init__", return_value=None)
        tracker_mock = mocker.MagicMock()
        tracker_mock.monthly_summary.return_value = {
            "period": "month",
            "total_tokens": 50000,
            "total_cost_estimate": "¥0.12",
            "by_operation": [],
        }
        mocker.patch("src.api.routes.misc.TokenTracker", return_value=tracker_mock)

        response = client.get("/v1/usage?period=month")
        assert response.status_code == 200
        assert response.json()["period"] == "month"


class TestGraphEndpoint:
    """GET /v1/graph 端点测试"""

    def test_graph_returns_json(self, client, mocker):
        """/v1/graph 返回图 JSON"""
        mock_dict = {
            "nodes": [{"id": "a.md", "degree": {"in": 1, "out": 0}}],
            "edges": [{"source": "b.md", "target": "a.md"}],
            "stats": {"total_nodes": 1, "total_edges": 1, "avg_degree": 1.0},
        }
        mocker.patch(
            "src.core.graph.WikiGraph.to_dict",
            return_value=mock_dict,
        )

        response = client.get("/v1/graph")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert "stats" in data
