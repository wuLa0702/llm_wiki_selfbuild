"""语义搜索 Pydantic 模型"""
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(description="搜索关键词", min_length=1)
    k: int = Field(default=10, description="最大返回条数", ge=1, le=100)
    method: str = Field(default="bm25", description="搜索模式: bm25 / vector / hybrid")


class SearchResultItem(BaseModel):
    """单条搜索结果"""
    path: str = ""
    score: float = 0
    snippet: str = ""
    metadata: dict = {}


class SearchResponse(BaseModel):
    """语义搜索响应"""
    results: list[SearchResultItem] = []
    total: int = 0
    enabled: bool = True
    error: str = ""
