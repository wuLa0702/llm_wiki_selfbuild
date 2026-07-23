"""
Agent 工具定义 — 3 个只读 @tool

复用现有 src/tools/ 和 src/core/，不做重复实现。
全部只读操作，Agent 零副作用。
"""
import logging
import os
from pathlib import Path

from langchain_core.tools import tool

from src.tools.search_tool import SearchTool
from src.tools.path_utils import safe_path

logger = logging.getLogger("agent.tools")

_WIKI_DIR = "wiki"


def _strip_frontmatter(content: str) -> str:
    """去掉 Markdown 文件的 YAML frontmatter"""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3:].strip()
    return content


@tool
def search_wiki(query: str) -> str:
    """搜索 Wiki 知识库，返回匹配页面列表（标题、路径、摘要）。

    当用户问问题时，优先使用此工具找到相关页面。
    返回每个页面的标题、路径和内容摘要，方便 Agent 决定读哪个页面。
    """
    logger.info("tool:search_wiki | query=%s", query)
    try:
        st = SearchTool()
        results = st.search(keyword=query, limit=8)
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
def read_page(path: str) -> str:
    """读取指定 Wiki 页面的完整正文内容。

    路径格式如 'entities/异步编程.md'。
    在 search_wiki 找到相关页面后，用此工具获取详细内容。

    返回去掉 frontmatter 后的正文，最长 4000 字。
    """
    logger.info("tool:read_page | path=%s", path)

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

    body = _strip_frontmatter(content)

    # 截断到 4000 字
    if len(body) > 4000:
        body = body[:4000] + "\n\n...（内容已截断）"

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
        from src.core.graph.graph import WikiGraph
        g = WikiGraph()
        g._ensure_built()

        # 从问题中提取关键词，找相关节点
        parts = []
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
            return f"未找到与问题直接相关的实体。知识库共有 {len(nodes)} 个页面。\n\n社区分布：\n{summary}" if summary else f"未找到相关实体。知识库共有 {len(nodes)} 个页面。"

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
