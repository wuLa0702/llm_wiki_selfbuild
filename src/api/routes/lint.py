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


@router.post("/v1/lint/fix")
async def lint_fix():
    """修复所有断链（删除受损链接标记）"""
    logger.info("POST /v1/lint/fix")
    compiler = WikiCompiler()
    result = compiler.lint(semantic=False)
    broken = result.get("broken_links", [])
    if not broken:
        return {"fixed": 0, "message": "没有断链需要修复"}

    from src.tools.read_tool import ReadTool
    from src.tools.write_tool import WriteTool
    import re

    reader = ReadTool("wiki")
    writer = WriteTool("wiki")
    fixed_count = 0

    for link in broken:
        source = link.get("source_page", "") if isinstance(link, dict) else ""
        target = link.get("broken_target", "") if isinstance(link, dict) else link
        if not source:
            continue
        try:
            content = reader.read_file(source)
        except Exception:
            continue

        # 删除 [[target]] 和 [[target|显示名]]
        pattern = r"\[\[" + re.escape(target) + r"(?:\|[^\]]*)?\]\]"
        new_content = re.sub(pattern, "", content)
        if new_content != content:
            writer.write_page(source, new_content, validate=False)
            fixed_count += 1

    return {"fixed": fixed_count, "message": f"已修复 {fixed_count} 个断链"}
