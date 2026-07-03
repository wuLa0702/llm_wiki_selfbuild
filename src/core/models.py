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


class QueryRequest(BaseModel):
    """Query 请求参数"""
    question: str


class QueryResponse(BaseModel):
    """Query 响应"""
    answer: str
    sources: list[str] = []
