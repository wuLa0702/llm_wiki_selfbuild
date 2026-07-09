"""
MCP Server 单元测试 — Phase 4 Step 9

通过 call_tool 入口模拟 MCP 协议调用，验证处理器行为。
"""
import asyncio
import json

from src.mcp_server import call_tool, _TOOL_REGISTRY, list_tools


def _call(name: str, args: dict) -> dict:
    """同步调用 MCP 工具"""
    result = asyncio.run(call_tool(name, args))
    return json.loads(result[0].text)


class TestMCPRegistry:
    """工具注册验证"""

    def test_all_tools_registered(self):
        """_TOOL_REGISTRY 包含所有 8 个工具"""
        names = {t["name"] for t in _TOOL_REGISTRY}
        expected = {"wiki_search", "wiki_read", "wiki_list", "wiki_graph",
                     "wiki_lint", "wiki_stats", "wiki_related", "wiki_insights"}
        assert names == expected

    def test_each_tool_has_handler(self):
        """每个工具都有 async handler"""
        for t in _TOOL_REGISTRY:
            assert asyncio.iscoroutinefunction(t["handler"]), f"{t['name']} handler not async"

    def test_list_tools_async(self):
        """list_tools 返回有效的 tool 列表"""
        tools = asyncio.run(list_tools())
        assert len(tools) == 8
        for tool in tools:
            assert tool.name.startswith("wiki_")
            assert tool.inputSchema is not None


class TestMCPHandlers:
    """MCP 工具调用测试"""

    def test_search_returns_results(self):
        data = _call("wiki_search", {"query": "Python", "limit": 5})
        assert "results" in data

    def test_search_empty_query(self):
        data = _call("wiki_search", {"query": ""})
        assert data["total"] == 0
        assert data["results"] == []

    def test_read_nonexistent(self):
        data = _call("wiki_read", {"path": "nonexistent.md"})
        assert "error" in data

    def test_list_returns_pages(self):
        data = _call("wiki_list", {})
        assert "pages" in data

    def test_list_by_type(self):
        data = _call("wiki_list", {"type": "entity"})
        for p in data["pages"]:
            assert p["type"] == "entity"

    def test_lint_returns_report(self):
        data = _call("wiki_lint", {})
        assert "summary" in data

    def test_stats_returns_counts(self):
        data = _call("wiki_stats", {})
        assert "total_pages" in data
        assert "type_distribution" in data

    def test_related_requires_path(self):
        data = _call("wiki_related", {})
        assert "error" in data
        assert "path" in data["error"].lower()

    def test_unknown_tool(self):
        data = _call("nonexistent", {})
        assert "error" in data
