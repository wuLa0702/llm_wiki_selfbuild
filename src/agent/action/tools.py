"""
Agent 工具定义 — 3 个只读 @tool

复用现有 src/tools/ 和 src/core/，不做重复实现。
全部只读操作，Agent 零副作用。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from langchain_core.tools import tool

from src.agent import constants as C
from src.tools.markdown_utils import strip_frontmatter
from src.tools.path_utils import safe_path
from src.tools.search_tool import SearchTool

logger = logging.getLogger("agent.tools")


# ── 模块级单例 ──────────────────────────────────────────────────────────────

_search_tool: SearchTool | None = None
_graph_instance: object | None = None


def _get_search_tool() -> SearchTool:
    global _search_tool
    if _search_tool is None:
        _search_tool = SearchTool()
    return _search_tool


def _get_graph():
    global _graph_instance
    if _graph_instance is None:
        from src.core.graph.graph import WikiGraph

        _graph_instance = WikiGraph()
    return _graph_instance


# ── 工具定义 ────────────────────────────────────────────────────────────────


@tool
def search_wiki(query: str) -> str:
    """搜索 Wiki 知识库，返回匹配页面列表（标题、路径、摘要）。

    当用户问问题时，优先使用此工具找到相关页面。
    返回每个页面的标题、路径和内容摘要，方便 Agent 决定读哪个页面。
    """
    logger.info(C.LOG_TOOL_SEARCH, query)
    try:
        search_tool = _get_search_tool()
        results = search_tool.search(keyword=query, limit=C.SEARCH_LIMIT)
    except Exception as e:
        logger.error(C.LOG_TOOL_SEARCH_FAILED, e)
        return C.ERROR_SEARCH_FAILED.format(query)

    if not results:
        return C.NO_MATCHES_MESSAGE

    lines: list[str] = []
    for r in results:
        path = r.get("path", "?")
        title = r.get("title") or Path(path).stem
        snippet = (r.get("snippet") or "")[:C.SNIPPET_MAX_CHARS].replace("\n", " ")
        score = r.get("score", 0)
        lines.append(f"- **{title}** (`{path}`) [匹配度 {score:{C.SCORE_FORMAT}}]\n  {snippet}")

    return "\n".join(lines)


@tool
def read_page(path: str, offset: int = 0, max_chars: int = C.READ_PAGE_MAX_CHARS) -> str:
    """读取指定 Wiki 页面的正文内容。

    路径格式如 'entities/异步编程.md'。
    在 search_wiki 找到相关页面后，用此工具获取详细内容。

    支持分页读取长文档：如果返回内容末尾有截断标记，
    可再次调用并设置 offset 参数继续读取后续内容。

    Args:
        path: 页面路径，如 'entities/异步编程.md'
        offset: 起始字符偏移位置（用于分页，首次调用传 0）
        max_chars: 最多返回字符数
    """
    logger.info(C.LOG_TOOL_READ, path, offset, max_chars)

    # 路径安全校验
    try:
        full_path = safe_path(C.WIKI_DIR, path)
    except PermissionError as e:
        logger.warning(C.LOG_TOOL_READ_UNAUTHORIZED, path)
        return C.ERROR_PATH_UNAUTHORIZED.format(e)

    if not os.path.isfile(full_path):
        logger.warning(C.LOG_TOOL_READ_NOT_FOUND, path)
        return C.ERROR_PAGE_NOT_FOUND.format(path)

    try:
        content = Path(full_path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.error(C.LOG_TOOL_READ_FAILED, path, e)
        return C.ERROR_READ_FAILED.format(e)

    body = strip_frontmatter(content)

    if offset > 0:
        body = body[offset:]

    if len(body) > max_chars:
        body = body[:max_chars] + C.TRUNCATION_MARKER

    if not body:
        return C.EMPTY_CONTENT_MESSAGE

    logger.info(C.LOG_TOOL_READ_SUCCESS, path, len(body))
    return body


@tool
def query_graph(question: str) -> str:
    """查询知识图谱，返回与问题相关的实体关联和社区信息。

    用于发现搜索关键词不直接匹配的隐含知识关联。
    例如问"X 和 Y 什么关系"时，图谱能找到页面间的连接。
    """
    logger.info(C.LOG_TOOL_GRAPH, question)
    try:
        g = _get_graph()
        g._ensure_built()

        parts: list[str] = []
        nodes = g.nodes()
        keywords = question.lower().replace("?", "").replace("，", " ").replace(" ", "_")
        matched = [n for n in nodes if any(k in n.lower() for k in keywords.split("_") if len(k) > 1)]

        if not matched:
            communities = g.communities()
            summary = "\n".join(
                f"- 社区 {cid}: {len(members)} 个页面"
                for cid, members in (communities or {}).items()
            )
            return (
                C.ERROR_NO_ENTITIES_WITH_COMMUNITIES.format(len(nodes), summary)
                if summary
                else C.ERROR_NO_ENTITIES.format(len(nodes))
            )

        for m in matched[:C.MATCHED_NODES_LIMIT]:
            neighbors = g.neighbors(m, depth=1)
            path_label = Path(m).stem
            if neighbors:
                neighbor_names = [Path(n).stem for n in neighbors[:C.NEIGHBOR_NODES_LIMIT]]
                parts.append(f"- **{path_label}** → 关联: {', '.join(neighbor_names)}")
            else:
                parts.append(f"- **{path_label}**（无直接关联）")

        return "\n".join(parts) if parts else C.ERROR_NO_ENTITIES.format(len(nodes))
    except Exception as e:
        logger.error(C.LOG_TOOL_GRAPH_FAILED, e)
        return C.ERROR_GRAPH_FAILED.format(e)
