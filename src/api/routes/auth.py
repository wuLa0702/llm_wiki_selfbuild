"""路由: 密码保护 — /v1/auth/*"""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.api.helpers import _get_pm
from src.models.auth import AuthMessageResponse, AuthProtectedResponse, AuthTokenResponse

logger = logging.getLogger("api.routes.auth")
router = APIRouter(tags=["auth"])


@router.post("/v1/auth/password", response_model=AuthMessageResponse)
async def set_password(request: Request):
    """设置 Wiki 访问密码"""
    body = await request.json()
    password = body.get("password", "").strip()
    if not password or len(password) < 4:
        return JSONResponse(status_code=400, content={"error": "密码至少 4 位"})
    pm = _get_pm()
    try:
        pm.set_password(password)
        return AuthMessageResponse(status="ok", message="密码已设置")
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@router.post("/v1/auth/verify", response_model=AuthTokenResponse)
async def verify_password(request: Request):
    """验证密码，返回访问 token"""
    body = await request.json()
    password = body.get("password", "").strip()
    if not password:
        return JSONResponse(status_code=400, content={"error": "password is required"})
    pm = _get_pm()
    if pm.verify(password):
        token = pm.create_token()
        return AuthTokenResponse(status="ok", token=token, expires_in=86400, message="验证通过")
    return JSONResponse(status_code=403, content={"error": "密码错误"})


@router.post("/v1/auth/clear", response_model=AuthMessageResponse)
async def clear_password():
    """清除密码（恢复公开访问）"""
    pm = _get_pm()
    if not pm.is_protected():
        return AuthMessageResponse(status="ok", message="当前未设置密码")
    pm.clear()
    return AuthMessageResponse(status="ok", message="密码已清除")


@router.get("/v1/auth/status", response_model=AuthProtectedResponse)
async def auth_status():
    """查询密码保护状态"""
    pm = _get_pm()
    return AuthProtectedResponse(protected=pm.is_protected(), active_tokens=pm.token_info()["active_tokens"])
