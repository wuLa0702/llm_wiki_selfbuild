"""语义搜索 Pydantic 模型"""
from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    """搜索请求"""
    query: str = Field(description="搜索关键词", min_length=1)
    k: int = Field(default=10, description="每页返回条数", ge=1, le=100)
    offset: int = Field(default=0, description="偏移量（用于翻页）", ge=0)
    method: str = Field(default="bm25", description="搜索模式: bm25 / vector / hybrid")


class MatchPosition(BaseModel):
    """文件中单处命中的位置信息"""
    section: str = ""       # 章节标题（如 "核心概念"）
    snippet: str = ""       # 该位置附近的匹配片段
    line: int = 0           # 在 .md 文件中的起始行号
    score: float = 0        # 该位置的局部匹配分（归一化 [0,1]）


class SearchResultItem(BaseModel):
    """单条搜索结果"""
    path: str = ""
    title: str = ""                      # 页面标题
    score: float = 0                     # 归一化得分 [0, 1]
    snippet: str = ""                    # 摘要片段
    metadata: dict = {}
    search_method: str = ""              # bm25 / vector / hybrid
    rrf_score: float = 0                 # RRF 融合分（混合模式）
    raw_score: float = 0                 # 原始得分（未归一化）
    match_positions: list[MatchPosition] = []  # 多命中位置


class SearchResponse(BaseModel):
    """语义搜索响应"""
    results: list[SearchResultItem] = []
    total: int = 0
    enabled: bool = True
    error: str = ""
    method: str = ""                     # 实际使用的搜索方法
    has_more: bool = False               # 是否有下一页
