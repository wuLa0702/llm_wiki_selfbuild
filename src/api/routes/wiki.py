"""路由: Wiki 浏览 — /wiki, /wiki/{path}, /wiki/graph, /wiki/query, /wiki/import"""
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.helpers import _check_page_access, _convert_wikilinks, _render_page_html
from src.db.repository import WikiRepository
from src.tools.read_tool import ReadTool

logger = logging.getLogger("api.routes.wiki")
router = APIRouter(tags=["wiki"])


@router.get("/wiki", response_class=HTMLResponse)
async def wiki_index():
    """Wiki 首页 — 列出所有页面"""
    reader = ReadTool("wiki")
    repo = WikiRepository()

    all_files = []
    for root, dirs, files in os.walk(reader.base_dir):
        for f in files:
            if f.endswith(".md"):
                rel = os.path.relpath(os.path.join(root, f), reader.base_dir).replace("\\", "/")
                all_files.append(rel)

    groups: dict[str, list[str]] = {"entity": [], "concept": [], "source": [], "query": [], "other": []}
    for f in sorted(all_files):
        page = repo.get_page(f)
        ptype = page["page_type"] if page else "other"
        if ptype not in groups:
            ptype = "other"
        groups[ptype].append(f)

    categories = [
        ("entity", "实体"), ("concept", "概念"),
        ("source", "来源"), ("query", "问答"), ("other", "其他"),
    ]

    sections = []
    for key, label in categories:
        pages = groups.get(key, [])
        if not pages:
            continue
        items = [f'<li><a href="/wiki/{p}" class="wikilink">{p}</a></li>' for p in pages]
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
<p>共 {len(all_files)} 个页面 · <a href="/wiki/query" class="wikilink">知识问答</a> · <a href="/wiki/graph" class="wikilink">图谱视图</a> · <a href="/wiki/import" class="wikilink">批量导入</a></p>
{''.join(sections)}
</body>
</html>"""
    return html


@router.get("/wiki/graph", response_class=HTMLResponse)
async def wiki_graph_viz():
    """Wiki 图谱可视化 — 从独立文件加载"""
    graph_html = Path("static/graph.html")
    if graph_html.exists():
        content = graph_html.read_text(encoding="utf-8")
        return HTMLResponse(content)
    return HTMLResponse("<h1>图谱页面未找到</h1><p>请确保 static/graph.html 存在</p>")


@router.get("/wiki/query", response_class=HTMLResponse)
async def wiki_query():
    """Wiki 知识问答 — 前端查询界面"""
    return HTMLResponse(Path("src/api/templates/query.html").read_text(encoding="utf-8"))


@router.get("/wiki/import", response_class=HTMLResponse)
async def wiki_import():
    """Wiki 批量导入 — 文件夹导入前端界面"""
    return HTMLResponse(Path("src/api/templates/import.html").read_text(encoding="utf-8"))


@router.get("/wiki/sources", response_class=HTMLResponse)
async def wiki_sources():
    """资料源浏览器 — 渐进滚动渲染"""
    return HTMLResponse(Path("src/api/templates/sources.html").read_text(encoding="utf-8"))


@router.get("/wiki/{page_path:path}", response_class=HTMLResponse)
async def wiki_page(page_path: str, request: Request):
    """渲染单个 Wiki 页面，[[双向链接]] 可点击跳转"""
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

    existing_pages: set[str] = set()
    for root, dirs, files in os.walk(reader.base_dir):
        for f in files:
            if f.endswith(".md"):
                rel = os.path.relpath(os.path.join(root, f), reader.base_dir).replace("\\", "/")
                existing_pages.add(rel)

    try:
        content = reader.read_file(page_path)
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"error": "Page not found", "path": page_path})
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"error": "Access denied", "detail": str(e)})

    return HTMLResponse(_render_page_html(page_path, content, existing_pages))
