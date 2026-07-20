"""
LLM Wiki — FastAPI 服务入口

职责：App 创建 + 中间件配置 + 路由注册 + 生命周期
"""
import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.app_state import init_services, shutdown_services
from src.api.errors import global_exception_handler
from src.api.middleware import setup_middleware
from src.api.routes import auth, graph, ingest, lint, misc, pages, purpose, sources, system

# 保持向后兼容 — 测试仍 import 这些符号
from src.api.helpers import (_check_page_access, _convert_wikilinks,
                             _get_pm, _get_token_from_request, _render_page_html)

logger = logging.getLogger("main")

app = FastAPI(
    title="LLM Wiki API",
    description="知识沉淀管理系统",
    version="0.1.0",
)

setup_middleware(app)
app.add_exception_handler(Exception, global_exception_handler)

# 挂载静态资源（CSS / JS / 图片）
_static_dir = os.environ.get("LLM_WIKI_RESOURCE_DIR", None)
_static_path = os.path.join(_static_dir, "static") if _static_dir else "static"
app.mount("/static", StaticFiles(directory=_static_path), name="static")

# 注册 API 路由（优先于 SPA）
app.include_router(auth.router)
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
_ui_dist = Path(__file__).resolve().parents[1] / "wiki-ui-v2" / "dist"
if _ui_dist.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_ui_dist / "assets")), name="ui_assets")

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


@app.on_event("startup")
async def _start_services():
    init_services()


@app.on_event("shutdown")
async def _stop_services():
    shutdown_services()
