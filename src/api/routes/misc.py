"""路由: 杂项 — /, /health, /v1/query, /v1/usage, /v1/watcher/*, /v1/privacy/*"""
import logging
import sqlite3

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from src.app_state import get_watcher, set_watcher
from src.core.privacy import PrivacyManager
from src.core.token_tracker import TokenTracker
from src.core.compiler import WikiCompiler
from src.models.common import (HealthResponse, PrivacyRuleListResponse,
                               PrivacyRuleResponse, RootResponse,
                               SourceInfo, SourceListResponse,
                               WatcherStatusResponse)
from src.models.query import QueryRequest, QueryResponse
from src.models.search import SearchRequest, SearchResponse, SearchResultItem
from src.models.usage import UsageResponse
from src.llm.adapter import LLMError

logger = logging.getLogger("api.routes.misc")
router = APIRouter(tags=["misc"])


@router.get("/")
async def root():
    """根路径 → 重定向到 Wiki 首页"""
    logger.debug("root endpoint 被调用，重定向到 /wiki")
    return RedirectResponse(url="/wiki")


@router.get("/health", response_model=HealthResponse)
async def health():
    logger.debug("health endpoint 被调用")

    import time

    # 近似运行时间
    startup_time = getattr(health, "_startup_ts", None)
    if startup_time is None:
        health._startup_ts = time.time()
        startup_time = time.time()
    uptime = time.time() - startup_time

    # 页面数
    total_pages = 0
    graph_nodes = 0
    graph_edges = 0
    ingest_pending = 0

    try:
        from src.db.repository import WikiRepository
        repo = WikiRepository()
        all_pages = repo.get_all_pages()
        total_pages = len(all_pages) if all_pages else 0
    except Exception:
        pass

    try:
        from src.core.compiler import WikiCompiler
        compiler = WikiCompiler()
        g = compiler.graph.to_dict(repo=compiler.repo)
        graph_nodes = len(g.get("nodes", []))
        graph_edges = len(g.get("edges", []))
    except Exception:
        pass

    try:
        from src.app_state import get_ingest_queue
        q = get_ingest_queue()
        if q and hasattr(q, "db_path"):
            conn = sqlite3.connect(q.db_path)
            row = conn.execute("SELECT COUNT(*) FROM ingest_queue WHERE status='pending'").fetchone()
            ingest_pending = row[0] if row else 0
            conn.close()
    except Exception:
        pass

    return HealthResponse(
        status="ok",
        version="0.1.0",
        uptime_seconds=round(uptime, 1),
        total_pages=total_pages,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        ingest_queue_pending=ingest_pending,
    )


# ------------------------------------------------------------------
# Query
# ------------------------------------------------------------------


@router.post("/v1/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """查询 Wiki 知识库，返回带 [[引用]] 的综合回答"""
    logger.info("POST /v1/query | question=%s archive=%s", request.question, request.archive)

    compiler = WikiCompiler()
    try:
        result = compiler.query(request.question, archive=request.archive)
        return QueryResponse(
            answer=result.get("answer", ""),
            sources=result.get("sources", []),
            confidence=result.get("confidence", "low"),
            gaps=result.get("gaps", []),
            archived=result.get("archived"),
        )
    except LLMError as e:
        logger.error("Query 失败 (LLM): %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": "LLM call failed", "detail": str(e), "code": "LLM_ERROR"},
        )
    except Exception as e:
        logger.error("Query 失败 (unexpected): %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal error", "detail": str(e), "code": "INTERNAL"},
        )


# ------------------------------------------------------------------
# Token Usage
# ------------------------------------------------------------------


@router.get("/v1/usage", response_model=UsageResponse)
async def get_usage(period: str = "today"):
    """查询 Token 消耗统计

    Args:
        period: today / week / month
    """
    logger.info("GET /v1/usage | period=%s", period)
    tracker = TokenTracker()
    if period == "month":
        result = tracker.monthly_summary()
    elif period == "week":
        result = tracker.weekly_summary()
    else:
        result = tracker.today_summary()
    return UsageResponse(**result)


# ------------------------------------------------------------------
# 语义搜索
# ------------------------------------------------------------------


@router.post("/v1/search", response_model=SearchResponse)
async def unified_search(request: SearchRequest):
    """统一搜索 Wiki 页面（BM25 / vector / hybrid）

    Request:
        {"query": "Python 异步", "k": 10, "method": "hybrid"}

    method 支持: bm25（默认）, vector（需启用 embedding）, hybrid（RRF 融合）
    """
    logger.info("POST /v1/search | query=%s k=%d method=%s",
                request.query, request.k, request.method)

    from src.core.search import get_search_engine

    engine = get_search_engine()
    method = getattr(request, "method", "bm25")

    results = engine.search(request.query, method=method, k=request.k)
    return SearchResponse(
        results=[SearchResultItem(**r) for r in results],
        total=len(results),
        enabled=True,
    )


# ------------------------------------------------------------------
# Source Watcher
# ------------------------------------------------------------------


@router.post("/v1/watcher/start", response_model=WatcherStatusResponse)
async def watcher_start():
    """启动 Source 文件夹自动监听"""
    logger.info("POST /v1/watcher/start")
    watcher = get_watcher()
    if watcher is None:
        from src.core.watcher import SourceWatcher
        watcher = SourceWatcher()
        set_watcher(watcher)
    if watcher.is_running:
        return WatcherStatusResponse(running=True, detail=watcher.status())
    watcher.start()
    return WatcherStatusResponse(running=True, detail=watcher.status())


@router.post("/v1/watcher/stop", response_model=WatcherStatusResponse)
async def watcher_stop():
    """停止 Source 文件夹自动监听"""
    logger.info("POST /v1/watcher/stop")
    watcher = get_watcher()
    if watcher is None or not watcher.is_running:
        return WatcherStatusResponse(running=False, detail="not_running")
    watcher.stop()
    return WatcherStatusResponse(running=False, detail="stopped")


@router.get("/v1/watcher/status", response_model=WatcherStatusResponse)
async def watcher_status():
    """查询 Source 监听状态"""
    logger.info("GET /v1/watcher/status")
    watcher = get_watcher()
    if watcher is None:
        return WatcherStatusResponse(running=False, detail="未启动")
    return WatcherStatusResponse(running=True, detail=watcher.status())


class WatcherConfigRequest(BaseModel):
    """Watcher 配置请求"""
    poll_interval: int = 10
    sources_dir: str = "raw/sources"


@router.post("/v1/watcher/config")
async def watcher_config(body: WatcherConfigRequest):
    """配置 Source 监听参数"""
    watcher = get_watcher()
    if watcher is None:
        return JSONResponse(status_code=400, content={"error": "Watcher 未启动，请先 POST /v1/watcher/start"})
    if watcher._running:
        return JSONResponse(status_code=400, content={"error": "请先停止 Watcher 再修改配置"})
    watcher.poll_interval = body.poll_interval
    watcher.sources_dir = body.sources_dir
    return {"status": "ok", "poll_interval": watcher.poll_interval, "sources_dir": watcher.sources_dir}


# ------------------------------------------------------------------
# Privacy Rules
# ------------------------------------------------------------------


@router.get("/v1/privacy/rules", response_model=PrivacyRuleListResponse)
async def list_privacy_rules():
    """查看所有隐私规则（含默认 + 用户自定义）"""
    pm = PrivacyManager()
    return PrivacyRuleListResponse(rules=pm.list_rules())


@router.post("/v1/privacy/rules", response_model=PrivacyRuleResponse)
async def add_privacy_rule(request: Request):
    """添加自定义隐私规则"""
    body = await request.json()
    keyword = body.get("keyword", "").strip()
    category = body.get("category", "general").strip()
    if not keyword:
        return JSONResponse(status_code=400, content={"error": "keyword is required"})
    pm = PrivacyManager()
    pm.add_rule(keyword, category)
    return PrivacyRuleResponse(keyword=keyword, category=category)


@router.delete("/v1/privacy/rules/{keyword}", response_model=PrivacyRuleResponse)
async def remove_privacy_rule(keyword: str):
    """删除用户自定义规则"""
    if not keyword.strip():
        return JSONResponse(status_code=400, content={"error": "keyword is required"})
    pm = PrivacyManager()
    pm.remove_rule(keyword.strip())
    return PrivacyRuleResponse(keyword=keyword.strip())


# ------------------------------------------------------------------
# 资料源列表
# ------------------------------------------------------------------


@router.get("/v1/sources", response_model=SourceListResponse)
async def list_sources(page: int = 1, per_page: int = 50):
    """分页列出 raw/sources/ 下的原始资料文件

    Args:
        page: 页码（从 1 开始）
        per_page: 每页条数（默认 50，最大 200）
    """
    import os
    from datetime import datetime

    logger.info("GET /v1/sources | page=%d per_page=%d", page, per_page)

    per_page = max(1, min(per_page, 200))
    sources_dir = "raw/sources"

    if not os.path.isdir(sources_dir):
        return SourceListResponse(sources=[], total=0, page=page, per_page=per_page, total_pages=0)

    all_files = []
    for root, dirs, files in os.walk(sources_dir):
        for f in sorted(files):
            if f.startswith("."):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, sources_dir).replace("\\", "/")
            stat = os.stat(full)
            all_files.append({
                "path": rel,
                "name": f,
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            })

    total = len(all_files)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = (page - 1) * per_page
    sliced = all_files[start:start + per_page]

    return SourceListResponse(
        sources=[SourceInfo(**s) for s in sliced],
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )

# ------------------------------------------------------------------
# 用户设置（JSON 文件持久化）
# ------------------------------------------------------------------
import json

class SettingsResponse(BaseModel):
    """系统设置（全部存 DB wiki_settings 表）"""
    # 用户偏好
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    output_language: str = "zh"
    search_method: str = "bm25"
    theme: str = "light"
    # 资料监控
    watcher_enabled: bool = False
    watcher_auto_extract: bool = True
    watcher_max_file_size_mb: int = 100
    watcher_allowed_extensions: str = ".md,.mdx,.txt,.pdf,.doc,.docx,.odt,.rtf,.pptx,.odp,.xls,.xlsx,.ods,.csv,.html,.htm"
    watcher_exclude_folders: str = ".git,.svn,.hg,.obsidian,.idea,.vscode,node_modules,.cache,__pycache__"
    watcher_exclude_extensions: str = "tmp,temp,bak,swp,part,partial,crdownload,exe,dll,so,dylib,bin,iso,dmg"
    watcher_exclude_patterns: str = "~$*,~lock~#*,*.draft.*,draft-*,*.private.*"


def _load_settings_from_db() -> dict:
    """从 wiki_settings 表读取全部设置"""
    from src.db.repository import WikiRepository
    repo = WikiRepository()
    defaults = SettingsResponse().model_dump()
    result = {}
    for key in defaults:
        val = repo.get_setting(f"settings.{key}")
        if val is not None:
            # 尝试 JSON 解析（列表/数字/bool），失败则原样返回
            try:
                result[key] = json.loads(val)
            except (json.JSONDecodeError, TypeError):
                result[key] = val
    defaults.update(result)
    return defaults


def _save_settings_to_db(data: dict) -> None:
    """全部设置写入 wiki_settings 表"""
    from src.db.repository import WikiRepository
    repo = WikiRepository()
    for key, val in data.items():
        repo.set_setting(f"settings.{key}", json.dumps(val, ensure_ascii=False))


@router.get("/v1/settings", response_model=SettingsResponse)
async def get_settings():
    """读取系统设置（DB wiki_settings 表）"""
    return SettingsResponse(**_load_settings_from_db())


@router.post("/v1/settings", response_model=SettingsResponse)
async def save_settings(body: SettingsResponse):
    """保存系统设置"""
    _save_settings_to_db(body.model_dump())
    return body
