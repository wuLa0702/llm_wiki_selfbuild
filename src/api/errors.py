"""
全局异常处理器 — 统一错误响应格式

所有未捕获异常收敛为 {"error": "...", "code": "..."} JSON 响应。
"""
import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("api.errors")


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """捕获所有未处理的异常，返回统一 JSON 错误"""
    logger.error(
        "未捕获异常 | path=%s method=%s error=%s",
        request.url.path, request.method, exc,
        exc_info=True,
    )
    return JSONResponse(
        status_code=500,
        content={"error": "Internal error", "code": "INTERNAL"},
    )
