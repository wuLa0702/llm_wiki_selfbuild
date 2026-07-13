"""
路由: 资料来源 — /v1/sources/*
"""
import logging
import os
import shutil

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.db.repository import WikiRepository

logger = logging.getLogger("api.routes.sources")
router = APIRouter(tags=["sources"])


# =====================================================================
# 目录树
# =====================================================================

def _list_dir(base: str) -> list[dict]:
    """递归列出目录结构"""
    items = []
    try:
        names = sorted(os.listdir(base))
    except PermissionError:
        return items
    for name in names:
        full = os.path.join(base, name)
        if name.startswith("."):
            continue
        if os.path.isdir(full):
            items.append({"name": name, "type": "directory", "path": full.replace("\\", "/"), "children": _list_dir(full)})
        else:
            items.append({"name": name, "type": "file", "path": full.replace("\\", "/"), "size": os.path.getsize(full)})
    return items


@router.get("/v1/sources/tree")
async def sources_tree():
    """返回 raw/sources/ 的完整目录树"""
    base = "raw/sources"
    if not os.path.isdir(base):
        return {"tree": [], "total_files": 0}
    tree = _list_dir(base)
    total = _count_files(tree)
    return {"tree": tree, "total_files": total}


def _count_files(tree: list[dict]) -> int:
    c = 0
    for item in tree:
        if item["type"] == "file":
            c += 1
        elif item["type"] == "directory":
            c += _count_files(item.get("children", []))
    return c


# =====================================================================
# 删除
# =====================================================================

def _cascade_delete_wiki(source_path: str) -> int:
    """删 DB + 文件中对应 source_file 的 wiki 页面，返回删除数"""
    repo = WikiRepository()
    conn = repo._get_connection()
    rows = conn.execute(
        "SELECT path FROM wiki_pages WHERE source_file = ?", (source_path,)
    ).fetchall()
    deleted = 0
    for row in rows:
        wiki_file = row["path"]
        # 删磁盘
        try:
            os.remove(os.path.normpath(wiki_file))
        except FileNotFoundError:
            pass
        # 删 DB
        conn.execute("DELETE FROM wiki_pages WHERE path = ?", (wiki_file,))
        conn.execute("DELETE FROM page_links WHERE source_path = ? OR target_path = ?", (wiki_file, wiki_file))
        deleted += 1
    conn.commit()
    conn.close()
    return deleted


@router.delete("/v1/sources/{source_path:path}")
async def delete_source(source_path: str):
    """删除单个源文件，级联删除关联 wiki 页面"""
    logger.info("DELETE /v1/sources/%s", source_path)

    # 安全校验：路径必须在 raw/sources/ 下
    full = os.path.normpath(source_path)
    safe_base = os.path.normpath("raw/sources")
    if not full.startswith(safe_base + os.sep) and full != safe_base:
        return JSONResponse(status_code=403, content={"error": "Access denied"})

    if not os.path.isfile(full):
        return JSONResponse(status_code=404, content={"error": "File not found", "path": source_path})

    wiki_deleted = _cascade_delete_wiki(source_path)
    os.remove(full)

    return {"status": "deleted", "source": source_path, "wiki_pages_deleted": wiki_deleted}


@router.delete("/v1/sources/folder/{folder_path:path}")
async def delete_source_folder(folder_path: str):
    """级联删除文件夹，级联删除关联 wiki 页面"""
    logger.info("DELETE /v1/sources/folder/%s", folder_path)

    full = os.path.normpath(folder_path)
    safe_base = os.path.normpath("raw/sources")
    if not full.startswith(safe_base + os.sep) and full != safe_base:
        return JSONResponse(status_code=403, content={"error": "Access denied"})

    if not os.path.isdir(full):
        return JSONResponse(status_code=404, content={"error": "Directory not found", "path": folder_path})

    # 统计所有子文件
    file_paths = []
    for root, dirs, files in os.walk(full):
        for f in files:
            fp = os.path.join(root, f).replace("\\", "/")
            file_paths.append(fp)

    total_wiki_deleted = 0
    for fp in file_paths:
        total_wiki_deleted += _cascade_delete_wiki(fp)

    shutil.rmtree(full)

    return {"status": "deleted", "folder": folder_path, "files_deleted": len(file_paths), "wiki_pages_deleted": total_wiki_deleted}


# =====================================================================
# 提取到 Wiki（异步 Agent）
# =====================================================================

class ExtractRequest(BaseModel):
    """大文件提取请求"""
    source_path: str


@router.post("/v1/sources/extract-to-wiki")
async def extract_to_wiki(body: ExtractRequest):
    """大文件 → Agent 多页面提取（异步，加入任务队列）"""
    source_path = body.source_path
    logger.info("POST /v1/sources/extract-to-wiki | %s", source_path)

    full = os.path.normpath(source_path)
    safe_base = os.path.normpath("raw/sources")
    if not full.startswith(safe_base + os.sep) and full != safe_base:
        return JSONResponse(status_code=403, content={"error": "Access denied"})
    if not os.path.isfile(full):
        return JSONResponse(status_code=404, content={"error": "File not found", "path": source_path})

    from src.core.compiler import WikiCompiler
    from src.app_state import get_task_queue

    compiler = WikiCompiler(task_queue=get_task_queue())

    try:
        result = compiler.ingest(source_path)
        return JSONResponse({"status": "ok", "message": "提取完成",
            "pages_created": result.get("pages_created", []),
            "pages_updated": result.get("pages_updated", [])})
    except Exception as e:
        logger.error("提取失败: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})
