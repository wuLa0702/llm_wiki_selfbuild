"""
LLM Wiki — FastAPI 服务入口

职责：App 创建 + 中间件配置 + 路由注册 + 生命周期
"""
import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.app_state import init_services, shutdown_services
from src.api.errors import global_exception_handler
from src.api.middleware import setup_middleware
from src.api.routes import auth, chat, graph, ingest, lint, misc, pages, purpose, sources, system
from src.utils.path_resolver import get_frontend_dist_dir, get_static_dir

# 保持向后兼容 — 测试仍 import 这些符号
from src.api.helpers import (_check_page_access, _convert_wikilinks,
                             _get_pm, _get_token_from_request, _render_page_html)

# 启动时：从 config.yaml 注入 API Key 到环境变量（优先级低于 .env）
from src.utils.config_manager import inject_config_to_env
inject_config_to_env()

logger = logging.getLogger("main")

app = FastAPI(
    title="LLM Wiki API",
    description="知识沉淀管理系统",
    version="0.1.0",
)

setup_middleware(app)
app.add_exception_handler(Exception, global_exception_handler)

# 挂载静态资源（CSS / JS / 图片）
# 开发模式：项目根/static/；打包模式：exe 内部 static/（只读）
_static_path = get_static_dir()
if os.path.isdir(_static_path):
    app.mount("/static", StaticFiles(directory=_static_path), name="static")
else:
    logger.warning("静态资源目录不存在，跳过挂载 | path=%s", _static_path)

# 注册 API 路由（优先于 SPA）
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(graph.router)
app.include_router(ingest.router)
app.include_router(lint.router)
app.include_router(misc.router)
app.include_router(pages.router)
app.include_router(purpose.router)
app.include_router(sources.router)
app.include_router(system.router)

logger.info("LLM Wiki API 启动 | version=0.1.0")

# ── SPA 前端（wiki-ui-v2/dist/） ──
# 迁移自 HeroUI → shadcn/ui，见 migration-audit.md
# 开发模式：CWD/wiki-ui-v2/dist/；打包模式：exe 内部 dist/
_ui_dist_path = get_frontend_dist_dir()
if _ui_dist_path:
    _ui_dist = Path(_ui_dist_path)
    assets_dir = _ui_dist / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="ui_assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_spa(full_path: str):
        # API 路径返回 404（让 API 路由处理）
        if full_path.startswith(("v1/", "health")):
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": "Not found"}, status_code=404)
        spa_index = _ui_dist / "index.html"
        if spa_index.exists():
            return FileResponse(str(spa_index))
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Not found"}, status_code=404)
else:
    logger.info("前端 dist 目录不存在，SPA 路由禁用（仅 API 模式）")


@app.on_event("startup")
async def _start_services():
    import time
    t0 = time.time()

    init_services()

    # 同步预热：构建图谱 + 计算关联度 + 写入 DB 缓存
    # 启动阶段多花几秒，换来第一个请求瞬时响应
    logger.info("启动预热：预构建知识图谱并写入缓存 ...")
    try:
        from src.core.graph.graph import WikiGraph
        await asyncio.to_thread(WikiGraph.compute_and_cache)
        elapsed = time.time() - t0
        logger.info("启动预热完成 | 耗时=%.1fs", elapsed)
    except Exception as exc:
        logger.warning("启动预热失败，后续请求将触发懒重建 | %s", exc)


@app.on_event("shutdown")
async def _stop_services():
    shutdown_services()
