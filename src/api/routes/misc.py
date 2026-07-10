"""路由: 杂项 — /, /health, /v1/query, /v1/usage, /v1/watcher/*, /v1/privacy/*"""
import logging

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
    return HealthResponse()


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

SETTINGS_FILE = "user_settings.json"

def _load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_settings(data: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class SettingsResponse(BaseModel):
    """用户设置"""
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    output_language: str = "zh"
    search_method: str = "bm25"
    theme: str = "light"


@router.get("/v1/settings", response_model=SettingsResponse)
async def get_settings():
    """读取用户设置"""
    saved = _load_settings()
    defaults = SettingsResponse().model_dump()
    defaults.update(saved)
    return SettingsResponse(**defaults)


@router.post("/v1/settings", response_model=SettingsResponse)
async def save_settings(body: SettingsResponse):
    """保存用户设置"""
    _save_settings(body.model_dump())
    return body
