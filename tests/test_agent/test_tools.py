"""
Agent 工具单元测试 — search_wiki, read_page, query_graph

Mock 策略：
  search_wiki  — mock SearchTool
  read_page    — 直接创建临时 wiki 文件（实际文件 IO）
  query_graph  — mock WikiGraph
"""
import os

import pytest

from src.agent.tools import search_wiki, read_page, query_graph


# ============================================================================
# search_wiki
# ============================================================================


class TestSearchWiki:
    """search_wiki 工具测试"""

    def test_search_returns_formatted_results(self, mocker):
        """搜索成功返回格式化的 Markdown 列表"""
        mock_search = mocker.patch("src.agent.tools.SearchTool")
        mock_instance = mock_search.return_value
        mock_instance.search.return_value = [
            {
                "path": "entities/python.md",
                "title": "Python 编程语言",
                "snippet": "Python 是一种通用编程语言",
                "score": 0.95,
            },
            {
                "path": "concepts/oop.md",
                "title": "面向对象编程",
                "snippet": "OOP 是一种编程范式",
                "score": 0.72,
            },
        ]

        result = search_wiki.invoke({"query": "Python"})

        assert "Python 编程语言" in result
        assert "entities/python.md" in result
        assert "面向对象编程" in result
        assert "匹配度" in result
        # 检查格式：每个结果应有 ` 包裹的路径
        assert "`entities/python.md`" in result
        assert "`concepts/oop.md`" in result

    def test_search_calls_search_tool(self, mocker):
        """search_wiki 使用 SearchTool 搜索"""
        mock_search = mocker.patch("src.agent.tools.SearchTool")
        mock_instance = mock_search.return_value
        mock_instance.search.return_value = []

        search_wiki.invoke({"query": "异步编程"})

        mock_search.assert_called_once()
        mock_instance.search.assert_called_once_with(keyword="异步编程", limit=8)

    def test_search_empty_results(self, mocker):
        """无匹配时返回友好提示"""
        mock_search = mocker.patch("src.agent.tools.SearchTool")
        mock_instance = mock_search.return_value
        mock_instance.search.return_value = []

        result = search_wiki.invoke({"query": "xyznonexistent"})

        assert "未找到" in result
        assert "匹配" in result

    def test_search_tool_error(self, mocker):
        """SearchTool 异常时返回错误信息"""
        mock_search = mocker.patch("src.agent.tools.SearchTool")
        mock_instance = mock_search.return_value
        mock_instance.search.side_effect = Exception("搜索服务不可用")

        result = search_wiki.invoke({"query": "test"})

        assert "搜索失败" in result
        assert "搜索服务不可用" in result


# ============================================================================
# read_page
# ============================================================================


class TestReadPage:
    """read_page 工具测试"""

    @pytest.fixture
    def wiki_dir(self, tmp_path, monkeypatch):
        """创建临时 wiki 目录，chdir 进去使工具读到此目录"""
        d = tmp_path / "wiki"
        d.mkdir()
        entities = d / "entities"
        entities.mkdir()

        # 带 frontmatter 的页面
        (entities / "python.md").write_text(
            "---\ntitle: Python\n---\n# Python 编程语言\n\nPython 是一种通用编程语言。\n",
            encoding="utf-8",
        )
        # 无 frontmatter 的页面
        (entities / "java.md").write_text(
            "# Java\n\nJava 是面向对象的编程语言。\n",
            encoding="utf-8",
        )

        # 模拟在项目根目录运行
        original_cwd = os.getcwd()
        os.chdir(tmp_path)
        yield d
        os.chdir(original_cwd)

    def test_read_page_with_frontmatter(self, wiki_dir):
        """有 frontmatter 的页面正确去除"""
        result = read_page.invoke({"path": "entities/python.md"})
        assert "# Python 编程语言" in result
        assert "---" not in result  # frontmatter 被去除
        assert "通用编程语言" in result

    def test_read_page_without_frontmatter(self, wiki_dir):
        """无 frontmatter 的页面正常返回"""
        result = read_page.invoke({"path": "entities/java.md"})
        assert "# Java" in result
        assert "面向对象" in result

    def test_read_page_file_not_found(self, wiki_dir):
        """不存在的页面返回友好提示"""
        result = read_page.invoke({"path": "entities/nonexistent.md"})
        assert "不存在" in result

    def test_read_page_path_traversal_rejected(self, wiki_dir):
        """路径穿越被拒绝"""
        result = read_page.invoke({"path": "../secret.md"})
        assert "越权" in result or "路径" in result or "Permission" in result

    def test_read_page_absolute_path_rejected(self, wiki_dir):
        """绝对路径被拒绝"""
        result = read_page.invoke({"path": "/etc/passwd"})
        assert "越权" in result or "路径" in result or "Permission" in result or "Absolute" in result

    def test_read_page_truncates_long_content(self, wiki_dir):
        """超长内容被截断"""
        long_content = "# 长页面\n\n" + "内容内容。" * 3000
        (wiki_dir / "long.md").write_text(long_content, encoding="utf-8")

        result = read_page.invoke({"path": "long.md"})
        assert "（内容已截断）" in result
        assert len(result) <= 4500  # 4000 + 截断提示

    def test_read_page_empty_file(self, wiki_dir):
        """空文件正常返回"""
        (wiki_dir / "empty.md").write_text("", encoding="utf-8")
        result = read_page.invoke({"path": "empty.md"})
        assert result == "" or not result  # 空内容


# ============================================================================
# query_graph
# ============================================================================


class TestQueryGraph:
    """query_graph 工具测试"""

    def test_query_graph_with_matches(self, mocker):
        """找到匹配节点时返回关联信息"""
        # WikiGraph 在 query_graph 函数内部延迟导入，需 patch 其源头
        mock_graph_class = mocker.patch("src.core.graph.graph.WikiGraph")
        mock_instance = mock_graph_class.return_value
        mock_instance.nodes.return_value = ["entities/python.md", "concepts/async.md", "entities/java.md"]
        mock_instance.neighbors.return_value = ["concepts/oop.md", "entities/java.md"]

        # 仅匹配 python
        result = query_graph.invoke({"question": "python"})

        # Path stem 为路径文件名（小写）
        assert "python" in result
        assert "关联" in result or "→" in result

    def test_query_graph_no_matches(self, mocker):
        """无匹配节点时反馈社区概览"""
        mock_graph_class = mocker.patch("src.core.graph.graph.WikiGraph")
        mock_instance = mock_graph_class.return_value
        mock_instance.nodes.return_value = ["entities/python.md", "entities/java.md"]
        mock_instance.communities.return_value = {0: ["entities/python.md", "entities/java.md"]}

        result = query_graph.invoke({"question": "量子计算"})

        assert "未找到" in result
        assert "社区" in result

    def test_query_graph_error(self, mocker):
        """WikiGraph 异常时返回错误信息"""
        mock_graph_class = mocker.patch("src.core.graph.graph.WikiGraph")
        mock_instance = mock_graph_class.return_value
        mock_instance.nodes.side_effect = Exception("图谱构建失败")

        result = query_graph.invoke({"question": "test"})

        assert "失败" in result

    def test_query_graph_empty_communities(self, mocker):
        """图谱有节点但无社区信息"""
        mock_graph_class = mocker.patch("src.core.graph.graph.WikiGraph")
        mock_instance = mock_graph_class.return_value
        mock_instance.nodes.return_value = ["entities/python.md"]
        mock_instance.communities.return_value = {}

        result = query_graph.invoke({"question": "test"})

        assert "未找到" in result or "社区" in result  # 至少返回节点数量
