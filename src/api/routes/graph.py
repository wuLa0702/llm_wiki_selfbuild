"""路由: 图谱 — /v1/graph, /v1/communities, /v1/insights"""
import json
import logging

from fastapi import APIRouter

from src.core.compiler import WikiCompiler
from src.models.graph import CommunitiesResponse, GraphResponse, InsightsResponse

logger = logging.getLogger("api.routes.graph")
router = APIRouter(tags=["graph"])


@router.get("/v1/graph", response_model=GraphResponse)
async def wiki_graph(min_weight: float = 0, max_edges: int = 0):
    """返回 Wiki 页面的关系图（JSON），含 4-signal 关联度数据和社区检测"""
    logger.info("GET /v1/graph | min_weight=%s max_edges=%s", min_weight, max_edges)
    compiler = WikiCompiler()
    result = compiler.graph.to_dict(repo=compiler.repo)

    total_edges = len(result.get("edges", []))
    if (min_weight > 0 or max_edges > 0) and result.get("edges"):
        edges = result["edges"]
        if min_weight > 0:
            edges = [e for e in edges if (e.get("weight") or 0) >= min_weight]
        if max_edges > 0:
            edges.sort(key=lambda e: e.get("weight") or 0, reverse=True)
            edges = edges[:max_edges]
        result["edges"] = edges
        result["stats"]["total_edges"] = len(edges)
        result["stats"]["filtered_from"] = total_edges
        logger.info("GET /v1/graph 边过滤 | %d → %d", total_edges, len(edges))

    body_size = len(json.dumps(result, ensure_ascii=False, default=str))
    if body_size > 500_000:
        logger.warning("GET /v1/graph 响应体过大 | edges=%d size=%.1fKB",
                       len(result.get("edges", [])), body_size / 1024)

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
