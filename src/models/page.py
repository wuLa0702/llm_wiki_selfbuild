"""Wiki 页面相关 Pydantic 模型"""
from datetime import datetime

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


class PageInfo(BaseModel):
    """页面列表中的单页信息"""
    path: str
    title: str
    page_type: str
    tags: list[str] = []
    word_count: int = 0
    updated_at: str = ""
    links_count: int = 0
    backlinks_count: int = 0


class PagesListResponse(BaseModel):
    """页面列表响应"""
    total: int
    pages: list[PageInfo] = []


class PageDetailResponse(BaseModel):
    """单页详情响应"""
    path: str
    title: str
    content: str
    page_type: str
    tags: list[str] = []
    links: list[str] = []
    backlinks: list[str] = []
    visibility: str = "public"
    created_at: str = ""
    updated_at: str = ""
