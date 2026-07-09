"""
MCP Server — 让外部 AI Agent（Claude Code 等）可直接搜索/读取 LLM Wiki

协议：Model Context Protocol (MCP)
传输模式：
  - stdio（默认）：本地 Claude Code 集成，配置到 .claude/mcp.json
  - http（--http 参数）：远程调用，FastAPI + uvicorn

启动：
  python src/mcp_server.py              # stdio 模式
  python src/mcp_server.py --http       # HTTP 模式（默认 8010 端口）

Phase 4 Step 9
"""
import argparse
import json
import logging
import os

import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions

from src.core.graph import WikiGraph
from src.core.compiler import WikiCompiler
from src.db.repository import WikiRepository
from src.tools.read_tool import ReadTool

# 禁用 MCP SDK 的日志输出（避免干扰 stdio 通信）
logging.getLogger("mcp").setLevel(logging.ERROR)

logger = logging.getLogger("mcp-server")
logger.setLevel(logging.INFO)
log_handler = logging.StreamHandler()
log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
logger.addHandler(log_handler)

server = Server("llm-wiki")

# ====================================================================
# 单例 — 连接隔离，读服务共享
# ====================================================================

_wiki_compiler: WikiCompiler | None = None


def get_compiler() -> WikiCompiler:
    """获取共享的 WikiCompiler 实例（懒加载单例）"""
    global _wiki_compiler
    if _wiki_compiler is None:
        _wiki_compiler = WikiCompiler()
        _wiki_compiler.graph._ensure_built(repo=_wiki_compiler.repo)
    return _wiki_compiler


def get_repo() -> WikiRepository:
    return get_compiler().repo


def get_reader() -> ReadTool:
    return ReadTool("wiki")


# ====================================================================
# 装饰器式工具注册 — 减少元编程量
# ====================================================================

_TOOL_REGISTRY: list[dict] = []  # [{name, description, inputSchema, handler}]


def wiki_tool(name: str, description: str, **schema_props):
    """装饰器：将 async 函数注册为 MCP 工具

    Usage:
        @wiki_tool(name="wiki_search", description="全文搜索", ...)
        async def handle_search(args: dict) -> dict: ...

    自动收集到 _TOOL_REGISTRY，list_tools() 和 call_tool() 从中读取。
    """
    def decorator(func):
        _TOOL_REGISTRY.append({
            "name": name,
            "description": description,
            "inputSchema": {
                "type": "object",
                "properties": schema_props.get("properties", {}),
                "required": schema_props.get("required", []),
            },
            "handler": func,
        })
        return func
    return decorator


# ====================================================================
# 工具定义 — 每个工具一行装饰器 + async handler
# ====================================================================


@wiki_tool(
    name="wiki_search",
    description="全文搜索 Wiki 页面（按标题/路径/标签匹配）",
    properties={"query": {"type": "string", "description": "搜索关键词"}, "limit": {"type": "integer", "description": "最大返回条数（默认 10）"}},
    required=["query"],
)
async def handle_search(args: dict) -> dict:
    query = args.get("query", "")
    limit = args.get("limit", 10)
    if not query.strip():
        return {"results": [], "total": 0}
    results = get_repo().search_pages(query, limit=limit)
    return {"results": results, "total": len(results)}


@wiki_tool(
    name="wiki_read",
    description="读取单个 Wiki 页面的完整 Markdown 内容",
    properties={"path": {"type": "string", "description": "页面路径，如 entities/python.md"}},
    required=["path"],
)
async def handle_read(args: dict) -> dict:
    path = _require(args, "path")
    content = get_reader().read_file(path)
    return {"path": path, "content": content, "length": len(content)}


@wiki_tool(
    name="wiki_list",
    description="按类型列出 Wiki 页面",
    properties={"type": {"type": "string", "description": "页面类型: entity / concept / source / query，不传返回全部"}},
)
async def handle_list(args: dict) -> dict:
    page_type = args.get("type")
    repo = get_repo()
    reader = get_reader()

    pages = []
    for root, _dirs, files in os.walk(reader.base_dir):
        for f in files:
            if not f.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(root, f), reader.base_dir).replace("\\", "/")
            meta = repo.get_page(rel)
            if meta is None:
                continue
            if page_type and meta.get("page_type") != page_type:
                continue
            pages.append({"path": rel, "title": meta.get("title", ""), "type": meta.get("page_type", "")})
    return {"pages": pages, "total": len(pages)}


@wiki_tool(
    name="wiki_graph",
    description="返回知识图谱 JSON 数据（节点 + 边 + 社区 + 洞察）",
)
async def handle_graph(args: dict) -> dict:
    c = get_compiler()
    return c.graph.to_dict(repo=c.repo)


@wiki_tool(
    name="wiki_lint",
    description="运行 Wiki 健康检查（断链/孤页/索引缺口/健康评分）",
)
async def handle_lint(args: dict) -> dict:
    return get_compiler().lint()


@wiki_tool(
    name="wiki_stats",
    description="返回知识库统计信息（页面数、类型分布、社区数等）",
)
async def handle_stats(args: dict) -> dict:
    repo = get_repo()
    c = get_compiler()

    all_pages = []
    reader = get_reader()
    for root, _dirs, files in os.walk(reader.base_dir):
        for f in files:
            if not f.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(root, f), reader.base_dir).replace("\\", "/")
            meta = repo.get_page(rel)
            if meta:
                all_pages.append(meta)

    type_dist: dict[str, int] = {}
    for p in all_pages:
        t = p.get("page_type", "other")
        type_dist[t] = type_dist.get(t, 0) + 1

    g = c.graph
    gd = g.to_dict(repo=c.repo)
    communities = {}
    try:
        communities = g.communities(repo=c.repo).get("communities", {})
    except Exception:
        pass

    return {
        "total_pages": len(all_pages),
        "type_distribution": type_dist,
        "total_nodes": gd["stats"]["total_nodes"],
        "total_edges": gd["stats"]["total_edges"],
        "avg_degree": gd["stats"]["avg_degree"],
        "community_count": len(communities),
    }


@wiki_tool(
    name="wiki_related",
    description="返回与指定页面最相关的 N 个页面（4-signal 关联度）",
    properties={"path": {"type": "string", "description": "页面路径"}, "limit": {"type": "integer", "description": "最大返回条数（默认 10）"}},
    required=["path"],
)
async def handle_related(args: dict) -> dict:
    path = _require(args, "path")
    limit = args.get("limit", 10)
    c = get_compiler()
    related = c.graph.related_pages(path, repo=c.repo, limit=limit)
    return {"path": path, "related": related, "total": len(related)}


@wiki_tool(
    name="wiki_insights",
    description="返回图谱洞察（惊奇连接 + 知识空白）",
)
async def handle_insights(args: dict) -> dict:
    c = get_compiler()
    comm_result = c.graph.communities(repo=c.repo)
    return c.graph.insights(comm_result, repo=c.repo)


# ====================================================================
# 内部工具
# ====================================================================


def _require(args: dict, key: str) -> str:
    """校验必填参数"""
    val = args.get(key, "").strip() if isinstance(args.get(key), str) else args.get(key)
    if not val:
        raise ValueError(f"缺少必填参数 '{key}'")
    return val


# ====================================================================
# MCP 协议绑定 — 零手工注册，从 _TOOL_REGISTRY 自动发现
# ====================================================================


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(name=t["name"], description=t["description"], inputSchema=t["inputSchema"])
        for t in _TOOL_REGISTRY
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """处理 MCP 工具调用 — 三级异常处理"""
    entry = next((t for t in _TOOL_REGISTRY if t["name"] == name), None)
    if entry is None:
        names = ", ".join(t["name"] for t in _TOOL_REGISTRY)
        return _err(f"未知工具: {name}，可用工具: {names}")

    try:
        result = await entry["handler"](arguments)
        return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except ValueError as e:
        logger.warning("MCP 参数错误 | tool=%s detail=%s", name, e)
        return _err(f"参数错误: {e}")
    except PermissionError as e:
        logger.warning("MCP 权限拒绝 | tool=%s detail=%s", name, e)
        return _err(f"权限拒绝: {e}")
    except FileNotFoundError as e:
        logger.warning("MCP 资源不存在 | tool=%s detail=%s", name, e)
        return _err(f"资源不存在: {e}")
    except Exception as exc:
        logger.exception("MCP 内部错误 | tool=%s", name)
        return _err("内部错误，请检查服务端日志")


def _err(msg: str) -> list[types.TextContent]:
    return [types.TextContent(type="text", text=json.dumps({"error": msg, "isError": True}, ensure_ascii=False))]


# ====================================================================
# 启动 — stdio / http 双模式
# ====================================================================


async def main_stdio() -> None:
    """stdio 模式：供本地 Claude Code 集成"""
    import mcp.server.stdio as _stdio

    async with _stdio.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, InitializationOptions(
            server_name="llm-wiki",
            server_version="0.1.0",
        ))


async def main_http(host: str = "0.0.0.0", port: int = 8010) -> None:
    """HTTP 模式：支持远程调用

    端点：POST /v1/mcp — 请求体 {tool_name, arguments}
    """
    from fastapi import FastAPI, Request
    from fastapi.responses import JSONResponse
    import uvicorn

    http_app = FastAPI(title="LLM Wiki MCP Server", version="0.1.0")

    @http_app.post("/v1/mcp")
    async def mcp_call(request: Request):
        body = await request.json()
        tool_name = body.get("tool_name", "")
        arguments = body.get("arguments", {})
        results = await call_tool(tool_name, arguments)
        return JSONResponse(content=json.loads(results[0].text))

    @http_app.get("/v1/mcp/tools")
    async def mcp_tools():
        return {"tools": [{"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]} for t in _TOOL_REGISTRY]}

    logger.info("MCP HTTP 模式启动 | http://%s:%d", host, port)
    uvicorn.run(http_app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import asyncio

    parser = argparse.ArgumentParser(description="LLM Wiki MCP Server")
    parser.add_argument("--http", action="store_true", help="以 HTTP 模式启动（默认 stdio）")
    parser.add_argument("--host", default="0.0.0.0", help="HTTP 监听地址")
    parser.add_argument("--port", type=int, default=8010, help="HTTP 监听端口")
    args = parser.parse_args()

    if args.http:
        asyncio.run(main_http(host=args.host, port=args.port))
    else:
        asyncio.run(main_stdio())
