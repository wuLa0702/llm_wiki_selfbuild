"""路由: 页面列表/详情 — /v1/pages, /v1/pages/{path}"""
import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.api.helpers import _check_page_access
from src.models.page import (
    PageActionResponse,
    PageDetailResponse,
    PageInfo,
    PagesListResponse,
    PageUpdateRequest,
)
from src.db.repository import WikiRepository
from src.tools.read_tool import ReadTool
from src.tools.write_tool import WriteTool

logger = logging.getLogger("api.routes.pages")
router = APIRouter(tags=["pages"])


@router.get("/v1/pages", response_model=PagesListResponse)
async def list_pages(page_type: str | None = None, limit: int = 50, offset: int = 0):
    """列出 Wiki 页面（JSON）"""
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


@router.get("/v1/pages/{page_path:path}/references")
async def get_page_references(page_path: str):
    """查询所有引用了该页面的文档路径列表"""
    logger.info("GET /v1/pages/%s/references", page_path)
    repo = WikiRepository()
    refs = repo.get_referencing_pages(page_path)
    return {"path": page_path, "references": refs, "count": len(refs)}


@router.get("/v1/pages/{page_path:path}", response_model=PageDetailResponse)
async def get_page_detail(page_path: str, request: Request):
    """获取单个 Wiki 页面的完整内容 + 元数据（JSON）"""
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

    # 查找关联的导入队列任务（含原始来源文件路径）
    ingest_job_id: str | None = None
    source_file: str | None = None
    try:
        file_name = os.path.basename(page_path)
        conn = repo._get_connection()
        row = conn.execute(
            "SELECT job_id, source_path FROM ingest_queue WHERE source_path LIKE ? ORDER BY updated_at DESC LIMIT 1",
            (f"%{file_name}%",),
        ).fetchone()
        conn.close()
        if row:
            ingest_job_id = row["job_id"]
            source_file = row["source_path"]
    except Exception:
        pass

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
        word_count=meta.get("word_count", 0),
        ingest_job_id=ingest_job_id,
        source_file=source_file,
    )


@router.post("/v1/pages/{page_path:path}", response_model=PageActionResponse)
async def update_page(page_path: str, body: PageUpdateRequest, request: Request):
    """更新 Wiki 页面内容"""
    logger.info("POST /v1/pages/%s", page_path)

    if not _check_page_access(request, page_path):
        return JSONResponse(status_code=403, content={"status": "error", "message": "Access denied"})

    writer = WriteTool("wiki")
    try:
        writer.write_page(page_path, body.content, validate=False)
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"status": "error", "message": str(e)})

    return PageActionResponse(status="ok", path=page_path, message="页面已更新")


@router.delete("/v1/pages/{page_path:path}", response_model=PageActionResponse)
async def delete_page(page_path: str, request: Request):
    """删除 Wiki 页面"""
    logger.info("DELETE /v1/pages/%s", page_path)

    if not _check_page_access(request, page_path):
        return JSONResponse(status_code=403, content={"status": "error", "message": "Access denied"})

    reader = ReadTool("wiki")
    full_path = os.path.normpath(os.path.join(reader.base_dir, page_path))
    if not full_path.startswith(os.path.normpath(reader.base_dir)):
        return JSONResponse(status_code=403, content={"status": "error", "message": "Path traversal"})

    try:
        os.remove(full_path)
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"status": "error", "message": "Page not found"})
    except PermissionError as e:
        return JSONResponse(status_code=403, content={"status": "error", "message": str(e)})

    return PageActionResponse(status="ok", path=page_path, message="页面已删除")
