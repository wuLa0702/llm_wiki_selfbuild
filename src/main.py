"""
LLM Wiki — FastAPI 服务入口
"""
import os
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from src.core.auth import PasswordManager, is_wiki_protected
from src.core.logging_config import configure_logging, get_logger
from src.core.graph import WikiGraph
from src.core.models import (
    IngestRequest,
    IngestResponse,
    PagesListResponse,
    PageDetailResponse,
    PageInfo,
    QueryRequest,
    QueryResponse,
    UsageResponse,
)
from src.core.privacy import PrivacyManager
from src.core.task_queue import TaskQueue
from src.core.token_tracker import TokenTracker
from src.core.watcher import SourceWatcher
from src.core.wiki_compiler import CompilerError, WikiCompiler
from src.db.repository import WikiRepository
from src.llm.adapter import LLMError
from src.tools.read_tool import ReadTool

configure_logging()
logger = get_logger("main")

app = FastAPI(
    title="LLM Wiki API",
    description="知识沉淀管理系统",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("LLM Wiki API 启动 | version=0.1.0")

# ------------------------------------------------------------------
# Source 自动监听（全局实例）
# ------------------------------------------------------------------

_watcher: SourceWatcher | None = None

# ------------------------------------------------------------------
# 任务队列（全局实例）
# ------------------------------------------------------------------

_task_queue: TaskQueue | None = None


def _rebuild_graph_handler(payload: dict) -> None:
    """后台重建图谱 + 关联度"""
    logger.info("后台任务开始重建图谱...")
    graph = WikiGraph()
    from src.db.repository import WikiRepository
    repo = WikiRepository()
    graph.build()
    graph.compute_relevance(repo)
    logger.info("后台任务图谱重建完成 | nodes=%d", len(graph.nodes()))


@app.on_event("startup")
async def _start_watcher():
    """服务启动时自动开启 Source 监听 + 任务队列"""
    global _watcher, _task_queue
    # 任务队列
    _task_queue = TaskQueue()
    _task_queue.register_handler("rebuild_graph", _rebuild_graph_handler)
    _task_queue.start()
    # Source 监听
    enabled = os.environ.get("WATCHER_ENABLED", "true").lower() not in ("false", "0", "no")
    if not enabled:
        logger.info("SourceWatcher 已禁用（WATCHER_ENABLED=false）")
        return
    _watcher = SourceWatcher(task_queue=_task_queue)
    _watcher.start()


@app.on_event("shutdown")
async def _stop_services():
    """服务关闭时停止后台服务"""
    global _watcher, _task_queue
    if _task_queue:
        _task_queue.stop()
    if _watcher and _watcher.is_running:
        _watcher.stop()


@app.get("/")
async def root():
    logger.debug("root endpoint 被调用")
    return {"message": "LLM Wiki is running", "version": "0.1.0"}


@app.get("/health")
async def health():
    logger.debug("health endpoint 被调用")
    return {"status": "ok"}


@app.post("/v1/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest):
    """Ingest 一个源文件到 Wiki 知识库"""
    logger.info("POST /v1/ingest | source_path=%s", request.source_path)

    compiler = WikiCompiler(task_queue=_task_queue)
    try:
        result = compiler.ingest(request.source_path)
        return result
    except CompilerError as e:
        logger.warning("Ingest failed: %s", e)
        return JSONResponse(
            status_code=404,
            content={"error": "Source not found", "detail": str(e), "code": "NOT_FOUND"},
        )
    except LLMError as e:
        logger.error("Ingest failed (LLM): %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": "LLM call failed", "detail": str(e), "code": "LLM_ERROR"},
        )
    except Exception as e:
        logger.error("Ingest failed (unexpected): %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal error", "detail": str(e), "code": "INTERNAL"},
        )


@app.post("/v1/query", response_model=QueryResponse)
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


@app.get("/v1/lint")
async def lint(semantic: bool = False):
    """运行 Wiki 健康检查

    Args:
        semantic: 设为 true 启用 LLM 语义检测（矛盾 + 缺口 + 浅页面，
                  结果缓存 1 小时）。默认 false 走静态检查。
    """
    logger.info("GET /v1/lint | semantic=%s", semantic)
    compiler = WikiCompiler()
    return compiler.lint(semantic=semantic)


# ==================================================================
# Phase 3 Step 6 — 页面列表 / 详情 / Usage API
# ==================================================================


@app.get("/v1/pages", response_model=PagesListResponse)
async def list_pages(
    page_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """列出 Wiki 页面（JSON）

    Args:
        page_type: 按类型过滤（entity / concept / source / query）
        limit: 每页数量（默认 50，最大 200）
        offset: 偏移量
    """
    logger.info("GET /v1/pages | type=%s limit=%d offset=%d", page_type, limit, offset)
    if limit < 1:
        limit = 50
    if limit > 200:
        limit = 200
    if offset < 0:
        offset = 0

    repo = WikiRepository()
    reader = ReadTool("wiki")

    all_pages: list[dict] = []
    for root, _dirs, files in os.walk(reader.base_dir):
        for f in files:
            if not f.endswith(".md"):
                continue
            rel = os.path.relpath(os.path.join(root, f), reader.base_dir).replace("\\", "/")
            meta = repo.get_page(rel)
            if meta is None:
                continue
            if page_type and meta.get("page_type") != page_type:
                continue
            all_pages.append(meta)

    all_pages.sort(key=lambda p: p.get("updated_at", ""), reverse=True)
    total = len(all_pages)
    sliced = all_pages[offset:offset + limit]

    pages_out = []
    for p in sliced:
        # 计算链接数量
        links = p.get("links", [])
        backlinks = p.get("backlinks", [])
        pages_out.append(PageInfo(
            path=p["path"],
            title=p.get("title", ""),
            page_type=p.get("page_type", ""),
            tags=p.get("tags", []),
            word_count=p.get("word_count", 0),
            updated_at=p.get("updated_at", ""),
            links_count=len(links),
            backlinks_count=len(backlinks),
        ))

    return PagesListResponse(total=total, pages=pages_out)


@app.get("/v1/pages/{page_path:path}", response_model=PageDetailResponse)
async def get_page_detail(page_path: str, request: Request):
    """获取单个 Wiki 页面的完整内容 + 元数据（JSON）

    Args:
        page_path: 页面路径，如 entities/python.md
    """
    logger.info("GET /v1/pages/%s", page_path)

    repo = WikiRepository()
    meta = repo.get_page(page_path)
    if meta is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Page not found", "detail": f"No metadata for '{page_path}'"},
        )

    # 密码保护检查
    if not _check_page_access(request, page_path):
        return JSONResponse(
            status_code=403,
            content={
                "path": page_path,
                "status": "locked",
                "message": "此页面需要密码验证，请先 POST /v1/auth/verify",
            },
        )

    reader = ReadTool("wiki")
    try:
        content = reader.read_file(page_path)
    except FileNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"error": "Page not found", "detail": f"File not found: '{page_path}'"},
        )
    except PermissionError as e:
        return JSONResponse(
            status_code=403,
            content={"error": "Access denied", "detail": str(e)},
        )

    visibility = meta.get("visibility", "public")

    return PageDetailResponse(
        path=page_path,
        title=meta.get("title", ""),
        content=content,
        page_type=meta.get("page_type", ""),
        tags=meta.get("tags", []),
        links=meta.get("links", []),
        backlinks=meta.get("backlinks", []),
        visibility=visibility,
        created_at=meta.get("created_at", ""),
        updated_at=meta.get("updated_at", ""),
    )


@app.get("/v1/usage", response_model=UsageResponse)
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


# ==================================================================
# Phase 3 Step 8 — Source 文件夹自动监听
# ==================================================================


@app.post("/v1/watcher/start")
async def watcher_start():
    """启动 Source 文件夹自动监听"""
    global _watcher
    logger.info("POST /v1/watcher/start")
    if _watcher is None:
        _watcher = SourceWatcher()
    if _watcher.is_running:
        return {"status": "already_running", "detail": _watcher.status()}
    _watcher.start()
    return {"status": "started", "detail": _watcher.status()}


@app.post("/v1/watcher/stop")
async def watcher_stop():
    """停止 Source 文件夹自动监听"""
    global _watcher
    logger.info("POST /v1/watcher/stop")
    if _watcher is None or not _watcher.is_running:
        return {"status": "not_running"}
    _watcher.stop()
    return {"status": "stopped"}


@app.get("/v1/watcher/status")
async def watcher_status():
    """查询 Source 监听状态"""
    global _watcher
    logger.info("GET /v1/watcher/status")
    if _watcher is None:
        return {"running": False, "detail": "未启动"}
    return _watcher.status()


@app.get("/v1/graph")
async def wiki_graph(min_weight: float = 0, max_edges: int = 0):
    """返回 Wiki 页面的关系图（JSON），含 4-signal 关联度数据和社区检测

    Args:
        min_weight: 边权重下限（过滤弱关联，默认 0=返回全部）
        max_edges: 最多返回的边数（按权重降序，默认 0=返回全部）
    """
    logger.info("GET /v1/graph | min_weight=%s max_edges=%s", min_weight, max_edges)
    compiler = WikiCompiler()
    result = compiler.graph.to_dict(repo=compiler.repo)

    total_edges = len(result.get("edges", []))
    if (min_weight > 0 or max_edges > 0) and result.get("edges"):
        edges = result["edges"]
        if min_weight > 0:
            edges = [e for e in edges if (e.get("weight") or 0) >= min_weight]
        if max_edges > 0:
            edges.sort(key=lambda e: e.get("weight") or 0, reverse=True)
            edges = edges[:max_edges]
        result["edges"] = edges
        result["stats"]["total_edges"] = len(edges)
        result["stats"]["filtered_from"] = total_edges
        logger.info("GET /v1/graph 边过滤 | %d → %d", total_edges, len(edges))

    # 响应体大小日志
    import json
    body_size = len(json.dumps(result, ensure_ascii=False, default=str))
    if body_size > 500_000:
        logger.warning("GET /v1/graph 响应体过大 | edges=%d size=%.1fKB", len(result.get("edges", [])), body_size / 1024)

    return result


@app.get("/v1/communities")
async def wikicommunities():
    """返回 Louvain 社区检测结果"""
    logger.info("GET /v1/communities")
    compiler = WikiCompiler()
    return compiler.graph.communities(repo=compiler.repo)


@app.get("/v1/insights")
async def wiki_insights():
    """返回图谱洞察（惊奇连接 + 知识空白）"""
    logger.info("GET /v1/insights")
    compiler = WikiCompiler()
    comm_result = compiler.graph.communities(repo=compiler.repo)
    return compiler.graph.insights(comm_result, repo=compiler.repo)


# ==================================================================
# 隐私规则 API
# ==================================================================


@app.get("/v1/privacy/rules")
async def list_privacy_rules():
    """查看所有隐私规则（含默认 + 用户自定义）"""
    pm = PrivacyManager()
    return {"rules": pm.list_rules()}


@app.post("/v1/privacy/rules")
async def add_privacy_rule(request: Request):
    """添加自定义隐私规则"""
    body = await request.json()
    keyword = body.get("keyword", "").strip()
    category = body.get("category", "general").strip()
    if not keyword:
        return JSONResponse(
            status_code=400,
            content={"error": "keyword is required"},
        )
    pm = PrivacyManager()
    pm.add_rule(keyword, category)
    return {"status": "ok", "keyword": keyword, "category": category}


@app.delete("/v1/privacy/rules/{keyword}")
async def remove_privacy_rule(keyword: str):
    """删除用户自定义规则"""
    if not keyword.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "keyword is required"},
        )
    pm = PrivacyManager()
    pm.remove_rule(keyword.strip())
    return {"status": "ok", "keyword": keyword.strip()}


# ==================================================================
# Phase 4 Step 6 — 密码保护
# ==================================================================


def _get_pm() -> PasswordManager:
    """获取 PasswordManager 实例"""
    return PasswordManager(WikiRepository())


@app.post("/v1/auth/password")
async def set_password(request: Request):
    """设置 Wiki 访问密码"""
    body = await request.json()
    password = body.get("password", "").strip()
    if not password or len(password) < 4:
        return JSONResponse(
            status_code=400,
            content={"error": "密码至少 4 位"},
        )
    pm = _get_pm()
    try:
        pm.set_password(password)
        return {"status": "ok", "message": "密码已设置"}
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})


@app.post("/v1/auth/verify")
async def verify_password(request: Request):
    """验证密码，返回访问 token"""
    body = await request.json()
    password = body.get("password", "").strip()
    if not password:
        return JSONResponse(
            status_code=400,
            content={"error": "password is required"},
        )
    pm = _get_pm()
    if pm.verify(password):
        token = pm.create_token()
        return {
            "status": "ok",
            "token": token,
            "expires_in": 86400,
            "message": "验证通过",
        }
    return JSONResponse(
        status_code=403,
        content={"error": "密码错误"},
    )


@app.post("/v1/auth/clear")
async def clear_password():
    """清除密码（恢复公开访问）"""
    pm = _get_pm()
    if not pm.is_protected():
        return {"status": "ok", "message": "当前未设置密码"}
    pm.clear()
    return {"status": "ok", "message": "密码已清除"}


@app.get("/v1/auth/status")
async def auth_status():
    """查询密码保护状态"""
    pm = _get_pm()
    return {
        "protected": pm.is_protected(),
        "active_tokens": pm.token_info()["active_tokens"],
    }


# ==================================================================
# Wiki 浏览路由
# ==================================================================


def _get_token_from_request(request: Request) -> str | None:
    """从请求中提取 token（优先 Authorization header，其次 query param）"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    token = request.query_params.get("token")
    return token


def _check_page_access(request: Request, page_path: str) -> bool:
    """检查是否有权限访问指定页面

    公开页面始终可访问。
    restricted 页面需要有效 token。

    Returns:
        True 允许访问，False 拒绝
    """
    repo = WikiRepository()
    meta = repo.get_page(page_path)
    if meta is None:
        return True  # 页面不存在，交给 404 处理
    visibility = meta.get("visibility", "public")
    if visibility != "restricted":
        return True
    # restricted 页面需要验证 token
    token = _get_token_from_request(request)
    if not token:
        return False
    pm = _get_pm()
    return pm.validate_token(token)


def _convert_wikilinks(text: str, existing_pages: set | None = None) -> str:
    """将 [[path|显示名]] 和 [[path]] 转换为 HTML 链接

    Args:
        text: 原始 Markdown 文本
        existing_pages: 已知存在的页面集合，用于判断断链
    """
    def replace(match):
        target = match.group(1).strip()
        display = match.group(2).strip() if match.group(2) else target
        css_class = "wikilink"
        if existing_pages is not None and target not in existing_pages:
            css_class = "wikilink broken"
        return f'<a href="/wiki/{target}" class="{css_class}">{display}</a>'

    return re.sub(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]", replace, text)


def _render_page_html(path: str, content: str, existing_pages: set | None = None) -> str:
    """将 Markdown 内容渲染为完整 HTML 页面"""
    import markdown

    # 转换 [[wikilinks]]
    linked = _convert_wikilinks(content, existing_pages)

    # Markdown → HTML
    body = markdown.markdown(linked, extensions=["extra", "fenced_code"])

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{path}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 2em; line-height: 1.7; }}
  a.wikilink {{ color: #2a5db0; text-decoration: none; border-bottom: 1px dashed #2a5db0; }}
  a.wikilink:hover {{ border-bottom-style: solid; }}
  a.wikilink.broken {{ color: #c0392b; border-bottom: 1px dashed #c0392b; }}
  .breadcrumb {{ color: #888; margin-bottom: 1em; }}
  .breadcrumb a {{ color: #2a5db0; }}
  pre {{ background: #f5f5f5; padding: 1em; border-radius: 4px; overflow-x: auto; }}
  blockquote {{ border-left: 3px solid #ddd; margin-left: 0; padding-left: 1em; color: #666; }}
</style>
</head>
<body>
<div class="breadcrumb"><a href="/wiki">Wiki 首页</a> / {path}</div>
{body}
</body>
</html>"""


@app.get("/wiki", response_class=HTMLResponse)
async def wiki_index():
    """Wiki 首页 — 列出所有页面"""
    reader = ReadTool("wiki")
    repo = WikiRepository()

    # 获取所有 .md 文件
    all_files = []
    for root, dirs, files in os.walk(reader.base_dir):
        for f in files:
            if f.endswith(".md"):
                rel = os.path.relpath(
                    os.path.join(root, f), reader.base_dir
                ).replace("\\", "/")
                all_files.append(rel)

    # 按类型分组
    groups: dict[str, list[str]] = {"entity": [], "concept": [], "source": [], "query": [], "other": []}
    for f in sorted(all_files):
        page = repo.get_page(f)
        ptype = page["page_type"] if page else "other"
        if ptype not in groups:
            ptype = "other"
        groups[ptype].append(f)

    # 渲染分组 HTML（ptype 用复数形式显示）
    categories = [
        ("entity", "实体"),
        ("concept", "概念"),
        ("source", "来源"),
        ("query", "问答"),
        ("other", "其他"),
    ]

    sections = []
    for key, label in categories:
        pages = groups.get(key, groups.get(key[:-1], []))
        if not pages:
            continue
        items = [
            f'<li><a href="/wiki/{p}" class="wikilink">{p}</a></li>'
            for p in pages
        ]
        sections.append(f"<h2>{label} ({len(pages)})</h2><ul>{''.join(items)}</ul>")

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLM Wiki</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 2em; line-height: 1.7; }}
  a.wikilink {{ color: #2a5db0; text-decoration: none; }}
  a.wikilink:hover {{ text-decoration: underline; }}
  ul {{ list-style: none; padding-left: 1em; }}
  li {{ padding: 0.2em 0; }}
  h2 {{ border-bottom: 1px solid #eee; padding-bottom: 0.3em; margin-top: 1.5em; }}
</style>
</head>
<body>
<h1>LLM Wiki 知识库</h1>
<p>共 {len(all_files)} 个页面 · <a href="/wiki/query" class="wikilink">知识问答</a> · <a href="/wiki/graph" class="wikilink">图谱视图</a></p>
{''.join(sections)}
</body>
</html>"""
    return html


@app.get("/wiki/graph", response_class=HTMLResponse)
async def wiki_graph_viz():
    """Wiki 图谱可视化 — 从独立文件加载，避免内联转义问题"""
    graph_html = Path("static/graph.html")
    if graph_html.exists():
        content = graph_html.read_text(encoding="utf-8")
        return HTMLResponse(content)
    return HTMLResponse("<h1>图谱页面未找到</h1><p>请确保 static/graph.html 存在</p>")


@app.get("/wiki/query", response_class=HTMLResponse)
async def wiki_query():
    """Wiki 知识问答 — 前端查询界面"""
    return HTMLResponse("""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>知识问答 — LLM Wiki</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 720px; margin: 0 auto; padding: 2em; line-height: 1.7; }
  a { color: #2a5db0; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .header { margin-bottom: 1.5em; color: #888; font-size: 14px; }
  .header a { color: #2a5db0; }
  .input-row { display: flex; gap: 8px; margin-bottom: 1.5em; }
  .input-row input { flex: 1; padding: 10px 14px; font-size: 15px; border: 1px solid #ddd; border-radius: 6px; outline: none; }
  .input-row input:focus { border-color: #2a5db0; box-shadow: 0 0 0 2px rgba(42,93,176,0.1); }
  .input-row button { padding: 10px 24px; font-size: 15px; background: #2a5db0; color: #fff; border: none; border-radius: 6px; cursor: pointer; }
  .input-row button:hover { background: #1d4a8e; }
  .input-row button:disabled { background: #95a5a6; cursor: not-allowed; }
  .options { margin-bottom: 1em; font-size: 13px; color: #666; }
  .options label { cursor: pointer; }
  .options input { margin-right: 4px; }
  .answer-box { border: 1px solid #e0e0e0; border-radius: 8px; padding: 1.2em 1.5em; margin-top: 0.5em; min-height: 60px; display: none; }
  .answer-box.show { display: block; }
  .answer-box.loading { display: flex; align-items: center; justify-content: center; color: #888; min-height: 80px; }
  .answer-box.loading::after { content: ''; width: 18px; height: 18px; margin-left: 8px; border: 2px solid #ddd; border-top-color: #2a5db0; border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .answer-box.error { border-color: #e74c3c; background: #fdf0ef; }
  .meta { font-size: 13px; color: #888; margin-top: 1em; padding-top: 0.8em; border-top: 1px solid #eee; }
  .meta span { margin-right: 1em; }
  .conf-high { color: #27ae60; } .conf-medium { color: #f39c12; } .conf-low { color: #e74c3c; }
  .sources { margin-top: 0.8em; }
  .sources a { display: inline-block; margin-right: 0.5em; }
  .gaps { margin-top: 0.5em; font-size: 13px; color: #e67e22; }
  .hint { color: #aaa; font-size: 13px; text-align: center; padding: 2em 0; }
  .archived { color: #27ae60; font-size: 13px; margin-top: 0.5em; }
</style>
</head>
<body>
<div class="header"><a href="/wiki">&larr; Wiki 首页</a></div>

<div class="input-row">
  <input id="queryInput" type="text" placeholder="向知识库提问…" autofocus>
  <button id="queryBtn" onclick="doQuery()">查询</button>
</div>

<div class="options">
  <label><input type="checkbox" id="archiveCheck"> 归档答案到 wiki/queries/</label>
</div>

<div id="answerBox" class="answer-box"></div>
<div id="hint" class="hint">输入问题后点击查询，LLM 将基于 Wiki 知识库回答。</div>

<script>
function doQuery() {
  const q = document.getElementById('queryInput').value.trim();
  if (!q) return;
  const btn = document.getElementById('queryBtn');
  const box = document.getElementById('answerBox');
  const hint = document.getElementById('hint');
  hint.style.display = 'none';
  box.className = 'answer-box loading';
  box.style.display = 'flex';
  box.textContent = '查询中…';
  btn.disabled = true;

  const archive = document.getElementById('archiveCheck').checked;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);

  fetch('/v1/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: q, archive }),
    signal: controller.signal,
  })
  .then(r => r.json())
  .then(data => {
    clearTimeout(timer);
    if (data.error) { showError(data.error); return; }
    renderAnswer(data);
  })
  .catch(err => {
    clearTimeout(timer);
    if (err.name === 'AbortError') {
      showError('请求超时（10s），LLM 回答较慢，请稍后重试');
    } else {
      showError('网络错误：' + err.message);
    }
  })
  .finally(() => { btn.disabled = false; });
}

function renderAnswer(data) {
  const box = document.getElementById('answerBox');
  const answer = wikilinksToHtml(data.answer || '');
  const conf = data.confidence || 'low';
  const confLabels = { high: '高', medium: '中', low: '低' };
  const confClass = 'conf-' + conf;

  let html = '<div>' + answer + '</div>';
  html += '<div class="meta">';
  html += '<span class="' + confClass + '">置信度: ' + confLabels[conf] + '</span>';
  if (data.sources && data.sources.length) {
    html += '<span>来源: ' + data.sources.map(s =>
      '<a href="/wiki/' + s + '">' + s.split('/').pop().replace(/\\.md$/, '') + '</a>'
    ).join(', ') + '</span>';
  }
  html += '</div>';

  if (data.gaps && data.gaps.length) {
    html += '<div class="gaps">⚠ 知识缺口: ' + data.gaps.join('; ') + '</div>';
  }
  if (data.archived) {
    html += '<div class="archived">✓ 已归档: <a href="/wiki/' + data.archived + '">' + data.archived + '</a></div>';
  }

  box.className = 'answer-box show';
  box.innerHTML = html;
}

function showError(msg) {
  const box = document.getElementById('answerBox');
  box.className = 'answer-box show error';
  box.innerHTML = '<strong>出错了</strong><br>' + msg;
}

function wikilinksToHtml(text) {
  return text.replace(/\\[\\[([^\\]|]+?)(?:\\|([^\\]]+?))?\\]\\]/g, function(match, target, display) {
    const label = display || target;
    return '<a href="/wiki/' + target + '">' + label + '</a>';
  });
}

document.getElementById('queryInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') doQuery();
});
</script>
</body>
</html>""")

@app.get("/wiki/{page_path:path}", response_class=HTMLResponse)
async def wiki_page(page_path: str, request: Request):
    """渲染单个 Wiki 页面，[[双向链接]] 可点击跳转"""
    # 密码保护检查
    if not _check_page_access(request, page_path):
        return HTMLResponse(f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="utf-8"><title>页面已锁定</title>
<style>body {{ font-family: -apple-system, sans-serif; max-width: 600px; margin: 2em auto; padding: 2em; text-align: center; }}
.lock-icon {{ font-size: 48px; margin-bottom: 0.5em; }}
h1 {{ font-size: 20px; color: #2c3e50; }}
p {{ color: #888; }}</style>
</head>
<body>
<div class="lock-icon">🔒</div>
<h1>此页面需要密码验证</h1>
<p>该页面标记为私人内容，请先通过 API 验证后再访问。</p>
</body>
</html>""")

    reader = ReadTool("wiki")

    # 收集所有存在的页面路径，用于标记断链
    existing_pages: set[str] = set()
    for root, dirs, files in os.walk(reader.base_dir):
        for f in files:
            if f.endswith(".md"):
                rel = os.path.relpath(
                    os.path.join(root, f), reader.base_dir
                ).replace("\\", "/")
                existing_pages.add(rel)

    try:
        content = reader.read_file(page_path)
    except FileNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"error": "Page not found", "path": page_path},
        )
    except PermissionError as e:
        return JSONResponse(
            status_code=403,
            content={"error": "Access denied", "detail": str(e)},
        )

    return HTMLResponse(_render_page_html(page_path, content, existing_pages))
