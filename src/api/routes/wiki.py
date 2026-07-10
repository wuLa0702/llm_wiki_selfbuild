"""路由: Wiki 浏览 — /wiki, /wiki/{path}, /wiki/graph, /wiki/query, /wiki/import"""
import logging
import os
from pathlib import Path

import markdown
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.helpers import _check_page_access, _convert_wikilinks
from src.config import templates
from src.db.repository import WikiRepository
from src.tools.read_tool import ReadTool

logger = logging.getLogger("api.routes.wiki")
router = APIRouter(tags=["wiki"])


def _find_suggestions(page_path: str, existing: set[str], max_count: int = 5) -> list[str]:
    """为 404 页面找相似的推荐页面"""
    suggestions: list[str] = []
    parts = page_path.replace(".md", "").split("/")
    prefix = "/".join(parts[:-1]) + "/" if len(parts) > 1 else ""
    if prefix:
        same_dir = sorted(p for p in existing if p.startswith(prefix))
        suggestions.extend(same_dir)
    if not suggestions:
        path_prefix = parts[0] if parts else ""
        if path_prefix:
            suggestions = sorted(p for p in existing if p.startswith(path_prefix + "/"))
    if not suggestions:
        suggestions = sorted(existing)
    return suggestions[:max_count]


def _group_citations(links: list[str]) -> dict[str, list[str]]:
    """按路径前缀将链接分组为 citations 面板数据"""
    labels = {
        "entities": "📄 实体", "concepts": "💡 概念",
        "sources": "📦 来源", "queries": "❓ 问答",
    }
    groups: dict[str, list[str]] = {}
    for link in links:
        prefix = link.split("/")[0] if "/" in link else "other"
        label = labels.get(prefix, "📎 其他")
        if label not in groups:
            groups[label] = []
        groups[label].append(link)
    return groups


@router.get("/wiki", response_class=HTMLResponse)
async def wiki_index(request: Request):
    """Wiki 首页 — 统计卡片 + 最近更新 + 图谱入口"""
    reader = ReadTool("wiki")
    repo = WikiRepository()

    all_files = []
    for root, dirs, files in os.walk(reader.base_dir):
        for f in files:
            if f.endswith(".md"):
                rel = os.path.relpath(os.path.join(root, f), reader.base_dir).replace("\\", "/")
                all_files.append(rel)

    stats = {"total": len(all_files), "entity_count": 0, "concept_count": 0, "source_count": 0, "query_count": 0}
    recent_pages = []

    for f in sorted(all_files):
        page = repo.get_page(f)
        ptype = page["page_type"] if page else "other"
        if ptype in stats:
            stats[f"{ptype}_count"] += 1
        if page:
            recent_pages.append({
                "path": f, "page_type": ptype,
                "updated_at": (page.get("updated_at") or page.get("created_at") or ""),
            })

    recent_pages.sort(key=lambda x: x["updated_at"], reverse=True)
    recent_pages = recent_pages[:10]

    return templates.TemplateResponse(
        request, "wiki/index.html",
        {"stats": stats, "recent_pages": recent_pages},
    )


@router.get("/wiki/graph", response_class=HTMLResponse)
async def wiki_graph_viz(request: Request):
    """Wiki 图谱可视化 — 使用 base 布局"""
    return templates.TemplateResponse(request, "wiki/graph.html", {})


@router.get("/wiki/query", response_class=HTMLResponse)
async def wiki_query(request: Request):
    """Wiki 知识问答 — 前端查询界面"""
    return templates.TemplateResponse(request, "query.html", {})


@router.get("/wiki/import", response_class=HTMLResponse)
async def wiki_import(request: Request):
    """Wiki 批量导入 — 文件夹导入前端界面"""
    return templates.TemplateResponse(request, "import.html", {})


@router.get("/wiki/sources", response_class=HTMLResponse)
async def wiki_sources(request: Request):
    """资料源浏览器 — 渐进滚动渲染"""
    return templates.TemplateResponse(request, "sources.html", {})


@router.get("/wiki/queue", response_class=HTMLResponse)
async def wiki_queue(request: Request):
    """摄入队列 — 活动面板"""
    return templates.TemplateResponse(request, "queue.html", {})


@router.get("/wiki/lint", response_class=HTMLResponse)
async def wiki_lint(request: Request):
    """Wiki 健康检查面板"""
    return templates.TemplateResponse(request, "wiki/lint.html", {})


@router.get("/wiki/settings", response_class=HTMLResponse)
async def wiki_settings(request: Request):
    """Wiki 设置页面"""
    return templates.TemplateResponse(request, "wiki/settings.html", {})


@router.get("/wiki/{page_path:path}", response_class=HTMLResponse)
async def wiki_page(page_path: str, request: Request):
    """渲染单个 Wiki 页面，[[双向链接]] 可点击跳转"""
    if not page_path or page_path.endswith("/"):
        return RedirectResponse(url="/wiki")

    if not _check_page_access(request, page_path):
        return templates.TemplateResponse(
            request, "wiki/error.html", {
                "error_code": 403, "error_title": "🔒 页面已锁定",
                "error_message": "此页面标记为私人内容，请先通过 API 验证后再访问。",
                "path": page_path,
            }, status_code=403,
        )

    reader = ReadTool("wiki")
    repo = WikiRepository()

    existing_pages: set[str] = set()
    for root, dirs, files in os.walk(reader.base_dir):
        for f in files:
            if f.endswith(".md"):
                rel = os.path.relpath(os.path.join(root, f), reader.base_dir).replace("\\", "/")
                existing_pages.add(rel)

    try:
        content = reader.read_file(page_path)
    except FileNotFoundError:
        suggestions = _find_suggestions(page_path, existing_pages)
        return templates.TemplateResponse(
            request, "wiki/error.html", {
                "error_code": 404, "error_title": "🕳️ 页面不存在",
                "error_message": f"你访问的页面 <code>{page_path}</code> 不存在。",
                "path": page_path, "suggestions": suggestions,
            }, status_code=404,
        )
    except PermissionError as e:
        return templates.TemplateResponse(
            request, "wiki/error.html", {
                "error_code": 403, "error_title": "🔒 访问被拒绝",
                "error_message": str(e), "path": page_path,
            }, status_code=403,
        )

    page_meta = repo.get_page(page_path)
    citations = _group_citations(page_meta.get("links", [])) if page_meta else {}
    linked = _convert_wikilinks(content, existing_pages)
    html_body = markdown.markdown(linked, extensions=["extra", "fenced_code"])

    parts = page_path.replace(".md", "").split("/")
    breadcrumbs = []
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        crumb_path = "/".join(parts[: i + 1]) + (".md" if is_last else "")
        breadcrumbs.append({"name": part, "path": crumb_path})

    return templates.TemplateResponse(
        request, "wiki/page.html", {
            "path": page_path, "html_body": html_body,
            "breadcrumbs": breadcrumbs, "page_meta": page_meta,
            "citations": citations,
        },
    )
