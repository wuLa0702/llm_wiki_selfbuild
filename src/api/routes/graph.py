"""路由: 图谱 — /v1/graph, /v1/communities, /v1/insights"""
import json
import logging

import networkx as nx
from fastapi import APIRouter

from src.core.compiler import WikiCompiler
from src.models.graph import CommunitiesResponse, GraphResponse, InsightsResponse

logger = logging.getLogger("api.routes.graph")
router = APIRouter(tags=["graph"])


def _compute_layout(nodes: list[dict], edges: list[dict]) -> dict[str, tuple[float, float]]:
    """用 networkx spring_layout 预计算节点坐标"""
    G = nx.Graph()
    for n in nodes:
        G.add_node(n["id"])
    for e in edges:
        G.add_edge(e.get("source") or e.get("from"), e.get("target") or e.get("to"))
    if G.number_of_nodes() == 0:
        return {}
    # 固定 seed，相同数据永远生成同一布局
    pos = nx.spring_layout(G, seed=42, k=2.5, iterations=50, scale=800)
    return {k: (float(v[0]), float(v[1])) for k, v in pos.items()}


@router.get("/v1/graph", response_model=GraphResponse)
async def wiki_graph(min_weight: float = 0, max_edges: int = 200, max_nodes: int = 0):
    """返回 Wiki 页面的关系图（JSON），含预计算坐标、社区检测、层级控制"""
    logger.info("GET /v1/graph | min_weight=%s max_edges=%s max_nodes=%s", min_weight, max_edges, max_nodes)
    compiler = WikiCompiler()
    result = compiler.graph.to_dict(repo=compiler.repo)

    # 边过滤
    total_edges = len(result.get("edges", []))
    if result.get("edges"):
        edges = result["edges"]
        if min_weight > 0:
            edges = [e for e in edges if (e.get("weight") or 0) >= min_weight]
        if max_edges > 0:
            edges.sort(key=lambda e: e.get("weight") or 0, reverse=True)
            edges = edges[:max_edges]
        result["edges"] = edges
        result["stats"]["total_edges"] = len(edges)
        result["stats"]["filtered_from"] = total_edges

    # 节点过滤：默认取 Top 30 高连接节点（max_nodes=30）
    nodes = result.get("nodes", [])
    if max_nodes > 0 and len(nodes) > max_nodes:
        nodes.sort(key=lambda n: (n.get("degree", {}).get("in", 0) + n.get("degree", {}).get("out", 0)), reverse=True)
        top_ids = {n["id"] for n in nodes[:max_nodes]}
        result["nodes"] = nodes[:max_nodes]
        # 只保留两端都在 top 内的边
        all_edges = result["edges"]
        result["edges"] = [e for e in all_edges if (e.get("source") or e.get("from")) in top_ids and (e.get("target") or e.get("to")) in top_ids]
        result["stats"]["total_nodes"] = len(result["nodes"])
        result["stats"]["total_edges"] = len(result["edges"])
        result["stats"]["filtered_nodes_from"] = len(nodes)

    # 计算静态布局坐标
    layout = _compute_layout(result["nodes"], result["edges"])
    for n in result["nodes"]:
        pos = layout.get(n["id"])
        if pos:
            n["x"] = pos[0]
            n["y"] = pos[1]

    logger.info("GET /v1/graph 布局完成 | nodes=%d edges=%d", len(result["nodes"]), len(result["edges"]))
    return result


@router.get("/v1/communities", response_model=CommunitiesResponse)
async def wikicommunities():
    """返回 Louvain 社区检测结果"""
    logger.info("GET /v1/communities")
    compiler = WikiCompiler()
    return compiler.graph.communities(repo=compiler.repo)


@router.get("/v1/insights", response_model=InsightsResponse)
async def wiki_insights():
    """返回图谱洞察（惊奇连接 + 知识空白）"""
    logger.info("GET /v1/insights")
    compiler = WikiCompiler()
    comm_result = compiler.graph.communities(repo=compiler.repo)
    return compiler.graph.insights(comm_result, repo=compiler.repo)
