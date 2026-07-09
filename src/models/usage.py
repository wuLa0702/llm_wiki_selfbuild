"""Usage / Token 相关 Pydantic 模型"""
from pydantic import BaseModel


class UsageResponse(BaseModel):
    """Token 用量响应"""
    period: str
    total_tokens: int
    total_cost_estimate: str
    by_operation: list[dict] = []
