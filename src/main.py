"""
LLM Wiki — FastAPI 服务入口
"""
import os
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from src.core.logging_config import configure_logging, get_logger
from src.core.models import IngestRequest, IngestResponse
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

    compiler = WikiCompiler()
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


@app.get("/v1/query")
async def query():
    """Query the wiki knowledge base (to be implemented)"""
    logger.info("GET /v1/query 被调用（桩代码）")
    return {"message": "Query endpoint — not yet implemented"}


@app.get("/v1/lint")
async def lint():
    """Check wiki health (to be implemented)"""
    logger.info("GET /v1/lint 被调用（桩代码）")
    return {"message": "Lint endpoint — not yet implemented"}


# ==================================================================
# Wiki 浏览路由
# ==================================================================


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
<p>共 {len(all_files)} 个页面</p>
{''.join(sections)}
</body>
</html>"""
    return html


@app.get("/wiki/{page_path:path}", response_class=HTMLResponse)
async def wiki_page(page_path: str):
    """渲染单个 Wiki 页面，[[双向链接]] 可点击跳转"""
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
