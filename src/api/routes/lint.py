"""路由: Lint — /v1/lint"""
import logging

from fastapi import APIRouter

from src.core.compiler import WikiCompiler
from src.models.common import LintResponse

logger = logging.getLogger("api.routes.lint")
router = APIRouter(tags=["lint"])


@router.get("/v1/lint", response_model=LintResponse)
async def lint(semantic: bool = False):
    """运行 Wiki 健康检查

    Args:
        semantic: 设为 true 启用 LLM 语义检测（矛盾 + 缺口 + 浅页面，
                  结果缓存 1 小时）。默认 false 走静态检查。
    """
    logger.info("GET /v1/lint | semantic=%s", semantic)
    compiler = WikiCompiler()
    return compiler.lint(semantic=semantic)
