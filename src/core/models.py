"""
数据模型 — Pydantic 定义
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class WikiPage(BaseModel):
    """Wiki 页面元数据"""
    path: str
    title: str
    page_type: str = Field(description="类型: entity / concept / source / query")
    tags: list[str] = []
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    backlinks: list[str] = []
    word_count: int = 0


class IngestRequest(BaseModel):
    """Ingest 请求参数"""
    source_path: str = Field(description="源文件路径（相对于 raw/sources/）")


class IngestResponse(BaseModel):
    """Ingest 响应"""
    status: str
    pages_created: list[str] = []
    pages_updated: list[str] = []
    message: str = ""
    confidence_summary: dict[str, int] = {}
    token_usage: dict | None = None


class QueryRequest(BaseModel):
    """Query 请求参数"""
    question: str = Field(description="查询问题", min_length=1)
    archive: bool = Field(default=False, description="是否将答案归档到 wiki/queries/")


class QueryResponse(BaseModel):
    """Query 响应"""
    answer: str
    sources: list[str] = []
    confidence: str = "low"
    gaps: list[str] = []
    archived: str | None = None


# ============================================================================
# Phase 2 — 结构化输出
# ============================================================================


class AnalysisItem(BaseModel):
    """分析结果中的单个实体或概念"""
    name: str
    importance: str = "medium"  # high / medium / low
    type: str = ""               # entity: person/book/tool/event
    description: str = ""        # concept: one sentence description
    related_to: list[str] = []


class Contradiction(BaseModel):
    """与现有页面的冲突"""
    claim: str = ""
    existing_page: str = ""
    description: str = ""


class Connection(BaseModel):
    """与现有 Wiki 页面的关联"""
    topic: str = ""
    wiki_page: str = ""
    relation: str = ""


class AnalysisOutput(BaseModel):
    """Step 1 分析输出的完整 JSON 结构"""
    entities: list[AnalysisItem] = []
    concepts: list[AnalysisItem] = []
    contradictions: list[Contradiction] = []
    connections_to_existing: list[Connection] = []
    recommendations: list[str] = []


# ============================================================================
# Phase 3 — Token 用量
# ============================================================================


class TokenUsageSummary(BaseModel):
    """Token 用量汇总响应"""
    period: str
    total_tokens: int
    total_cost_estimate: str
    by_operation: list[dict] = []
