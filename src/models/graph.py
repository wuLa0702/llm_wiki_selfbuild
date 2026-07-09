"""图谱相关 Pydantic 模型"""
from pydantic import BaseModel


class GraphStats(BaseModel):
    """图谱统计"""
    total_nodes: int = 0
    total_edges: int = 0
    avg_degree: float = 0.0
    filtered_from: int | None = None


class GraphResponse(BaseModel):
    """知识图谱完整响应"""
    nodes: list[dict] = []
    edges: list[dict] = []
    stats: GraphStats = GraphStats()
    communities: dict | None = None
    modularity: float = 0.0
    insights: list | dict | None = None
    surprising_connections: list = []
    knowledge_gaps: list = []


class CommunitiesResponse(BaseModel):
    """社区检测响应"""
    communities: dict = {}
    orphan_communities: list = []
    modularity: float = 0.0
    total_nodes: int = 0


class InsightsResponse(BaseModel):
    """图谱洞察响应"""
    surprising_connections: list = []
    knowledge_gaps: list = []
    summary: dict = {}
