"""路由: Lint — /v1/lint"""
import logging
import re

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
    """三层修复：建议修正→创建存根→补充缺失"""
    logger.info("POST /v1/lint/fix")
    compiler = WikiCompiler()
    result = compiler.lint(semantic=False)
    broken = result.get("broken_links", [])
    if not broken:
        return {"rewritten": 0, "stubs": 0, "filled": 0, "message": "没有需要修复的断链"}

    from src.tools.read_tool import ReadTool
    from src.tools.write_tool import WriteTool
    from src.core.lint.linter import suggest_correction, create_stub, fill_missing_links

    reader = ReadTool("wiki")
    writer = WriteTool("wiki")
    g = compiler.graph
    existing_nodes = set(g.nodes())

    rewritten = 0
    stubs = 0
    skipped = []

    for link in broken:
        source = link.get("source_page", "") if isinstance(link, dict) else ""
        target = link.get("broken_target", "") if isinstance(link, dict) else link
        if not source:
            continue
        try:
            content = reader.read_file(source)
        except Exception:
            continue

        # 策略1：模糊匹配修正
        suggestion = suggest_correction(target, existing_nodes, threshold=0.5)
        if suggestion and suggestion != target:
            pattern = r"\[\[" + re.escape(target) + r"(?:\|[^\]]*)?\]\]"
            new_content = re.sub(pattern, f"[[{suggestion}]]", content)
            if new_content != content:
                writer.write_page(source, new_content, validate=False)
                rewritten += 1
                continue

        # 策略2：创建存根
        stub_path = create_stub(target)
        if stub_path:
            stubs += 1
            continue

        skipped.append(target)

    # 策略3：补充缺失
    filled = fill_missing_links()

    return {
        "rewritten": rewritten,
        "stubs": stubs,
        "filled": filled,
        "skipped": len(skipped),
        "message": f"重写 {rewritten} 个 · 存根 {stubs} 个 · 补充 {filled} 个",
    }
