"""Query 相关 Pydantic 模型"""
from pydantic import BaseModel, Field


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


class QueryOutput(BaseModel):
    """LLM 回答的结构化输出（用于 Step 3 的 structured_llm 调用）"""
    answer: str
    confidence: str  # high / medium / low
    gaps: list[str] = []
