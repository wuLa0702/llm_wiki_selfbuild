"""Ingest 相关 Pydantic 模型"""
from pydantic import BaseModel, Field


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


class AnalysisItem(BaseModel):
    """分析结果中的单个实体或概念"""
    name: str
    importance: str = "medium"
    type: str = ""
    description: str = ""
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
