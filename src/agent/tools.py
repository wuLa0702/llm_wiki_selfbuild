"""
Agent 工具定义 — 3 个只读 @tool

复用现有 src/tools/ 和 src/core/，不做重复实现。
全部只读操作，Agent 零副作用。

修复记录（2026-07-23 宪宪-豆包 review）：
  - limit=8 → SEARCH_LIMIT 命名常量
  - SearchTool / WikiGraph 改为模块级单例，避免每次调用新建
  - _strip_frontmatter → 提取到 markdown_utils.py，消除 DRY 违反
  - read_page 增加 offset / max_chars 参数，支持分页读长文档
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from langchain_core.tools import tool

from src.tools.markdown_utils import strip_frontmatter
from src.tools.path_utils import safe_path
from src.tools.search_tool import SearchTool

logger = logging.getLogger("agent.tools")

_WIKI_DIR = "wiki"

# Agent 单次搜索最多返回 N 条结果
# 每条 snippet 约 120 字符，10 条 ≈ 1200 字符 ≈ 300 tokens，可控
SEARCH_LIMIT = 10

# read_page 单次读取最大字符数
READ_PAGE_MAX_CHARS = 4000

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
    logger.info("tool:search_wiki | query=%s", query)
    try:
        st = _get_search_tool()
        results = st.search(keyword=query, limit=SEARCH_LIMIT)
    except Exception as e:
        logger.error("search_wiki 失败 | error=%s", e)
        return f"搜索失败：{e}"

    if not results:
        return "未找到匹配的页面。"

    lines: list[str] = []
    for r in results:
        path = r.get("path", "?")
        title = r.get("title") or Path(path).stem
        snippet = (r.get("snippet") or "")[:200].replace("\n", " ")
        score = r.get("score", 0)
        lines.append(f"- **{title}** (`{path}`) [匹配度 {score:.2f}]\n  {snippet}")

    return "\n".join(lines)


@tool
def read_page(path: str, offset: int = 0, max_chars: int = READ_PAGE_MAX_CHARS) -> str:
    """读取指定 Wiki 页面的正文内容。

    路径格式如 'entities/异步编程.md'。
    在 search_wiki 找到相关页面后，用此工具获取详细内容。

    支持分页读取长文档：如果返回内容末尾有"（内容已截断）"，
    可再次调用并设置 offset 参数继续读取后续内容。

    Args:
        path: 页面路径，如 'entities/异步编程.md'
        offset: 起始字符偏移位置（用于分页，首次调用传 0）
        max_chars: 最多返回字符数，默认 4000

    Returns:
        去掉 frontmatter 后的正文片段
    """
    logger.info("tool:read_page | path=%s offset=%d max_chars=%d", path, offset, max_chars)

    # 路径安全校验
    try:
        full_path = safe_path(_WIKI_DIR, path)
    except PermissionError as e:
        logger.warning("read_page 路径越权 | path=%s", path)
        return f"路径越权：{e}"

    if not os.path.isfile(full_path):
        logger.warning("read_page 文件不存在 | path=%s", path)
        return f"页面不存在：{path}"

    try:
        content = Path(full_path).read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        logger.error("read_page 读取失败 | path=%s error=%s", path, e)
        return f"读取失败：{e}"

    body = strip_frontmatter(content)

    # 支持 offset 分页
    if offset > 0:
        body = body[offset:]

    # 截断到 max_chars
    if len(body) > max_chars:
        body = body[:max_chars] + "\n\n...（内容已截断）"

    if not body:
        return "（页面内容为空）"

    logger.info("tool:read_page 成功 | path=%s chars=%d", path, len(body))
    return body


@tool
def query_graph(question: str) -> str:
    """查询知识图谱，返回与问题相关的实体关联和社区信息。

    用于发现搜索关键词不直接匹配的隐含知识关联。
    例如问"X 和 Y 什么关系"时，图谱能找到页面间的连接。
    """
    logger.info("tool:query_graph | question=%s", question)
    try:
        g = _get_graph()
        g._ensure_built()

        # 从问题中提取关键词，找相关节点
        parts: list[str] = []
        nodes = g.nodes()
        # 找路径名包含关键词的节点
        keywords = question.lower().replace("?", "").replace("，", " ").replace(" ", "_")
        matched = [n for n in nodes if any(k in n.lower() for k in keywords.split("_") if len(k) > 1)]

        if not matched:
            # 没有精确匹配，返回社区概览
            communities = g.communities()
            summary = "\n".join(
                f"- 社区 {cid}: {len(members)} 个页面"
                for cid, members in (communities or {}).items()
            )
            return (
                f"未找到与问题直接相关的实体。知识库共有 {len(nodes)} 个页面。\n\n社区分布：\n{summary}"
                if summary
                else f"未找到相关实体。知识库共有 {len(nodes)} 个页面。"
            )

        # 对每个匹配节点找邻居
        for m in matched[:5]:
            neighbors = g.neighbors(m, depth=1)
            path_label = Path(m).stem
            if neighbors:
                neighbor_names = [Path(n).stem for n in neighbors[:8]]
                parts.append(f"- **{path_label}** → 关联: {', '.join(neighbor_names)}")
            else:
                parts.append(f"- **{path_label}**（无直接关联）")

        return "\n".join(parts) if parts else f"未找到相关实体。知识库共有 {len(nodes)} 个页面。"
    except Exception as e:
        logger.error("query_graph 失败 | error=%s", e)
        return f"图谱查询失败：{e}"
