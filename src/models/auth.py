"""认证/密码相关 Pydantic 模型"""
from pydantic import BaseModel


class AuthTokenResponse(BaseModel):
    """密码验证成功，返回 token"""
    status: str = "ok"
    token: str = ""
    expires_in: int = 86400
    message: str = "验证通过"


class AuthMessageResponse(BaseModel):
    """通用认证操作消息（set/clear 等）"""
    status: str
    message: str = ""


class AuthProtectedResponse(BaseModel):
    """密码保护状态"""
    protected: bool = False
    active_tokens: int = 0
