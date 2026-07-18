"""
路由: 资料来源 — /v1/sources/*
"""
import logging
import os
import shutil

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.core.logging_config import get_logger
from src.db.repository import WikiRepository

logger = get_logger("api.routes.sources")
router = APIRouter(tags=["sources"])


# =====================================================================
# 目录树
# =====================================================================

def _list_dir(base: str) -> list[dict]:
    """递归列出目录结构，按修改时间排序（目录优先，文件按 mtime 升序）"""
    items = []
    try:
        names = os.listdir(base)
    except PermissionError:
        return items
    entries = []
    for name in names:
        full = os.path.join(base, name)
        if name.startswith("."):
            continue
        if os.path.isdir(full):
            entries.append((name, "directory", _list_dir(full)))
        else:
            stat = os.stat(full)
            entries.append((name, "file", stat.st_mtime))
    # 目录在前，文件在后，各自按 mtime 升序
    entries.sort(key=lambda x: (0 if x[1] == "directory" else 1, x[2] if x[1] == "file" else 0))
    for name, typ, data in entries:
        full = os.path.join(base, name)
        if typ == "directory":
            items.append({"name": name, "type": "directory", "path": full.replace("\\", "/"), "children": data})
        else:
            items.append({"name": name, "type": "file", "path": full.replace("\\", "/"), "size": int(os.path.getsize(full))})
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
    """删除关联的 Wiki 页面（通过 sources frontmatter 匹配），返回删除数

    注意：wiki_pages 表中没有 source_file 字段（待 migration），
    所以目前 cascade 仅尝试匹配 frontmatter 中的 sources: 字段。
    匹配不到时静默返回 0，不影响源文件本身的删除。
    """
    import re
    import sqlite3
    from pathlib import Path

    wiki_dir = "wiki"
    deleted = 0
    source_ref = source_path.replace("\\", "/")

    if not os.path.isdir(wiki_dir):
        return 0

    for wiki_file in Path(wiki_dir).rglob("*.md"):
        try:
            content = wiki_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # 在 frontmatter 中找 sources: 字段
        m = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not m:
            continue
        frontmatter = m.group(1)
        if source_ref in frontmatter or os.path.basename(source_ref) in frontmatter:
            rel_path = str(wiki_file).replace("\\", "/")
            try:
                wiki_file.unlink()
            except OSError:
                pass
            # 删 DB
            try:
                conn = sqlite3.connect("wiki.db")
                conn.execute("DELETE FROM wiki_pages WHERE path = ?", (rel_path,))
                conn.execute("DELETE FROM page_links WHERE source_path = ? OR target_path = ?", (rel_path, rel_path))
                conn.commit()
                conn.close()
                deleted += 1
            except sqlite3.OperationalError:
                pass

    return deleted


@router.delete("/v1/sources/delete")
async def delete_source(path: str = ""):
    """删除单个源文件或空目录，级联删除关联 wiki 页面

    用 query parameter 传 path，避免 URL 路径编码问题。
    """
    raw_path = path
    path = path.strip().lstrip("/").replace("\\", "/")
    logger.info("DELETE /v1/sources/delete | raw=%s cleaned=%s", raw_path, path)

    if not path:
        logger.warning("DELETE 拒绝: path 为空 | raw=%s", raw_path)
        return JSONResponse(status_code=400, content={"error": "path is required"})

    # 安全校验：路径必须在 raw/sources/ 下
    safe_prefix = "raw/sources/"
    if not path.startswith(safe_prefix):
        logger.warning("DELETE 安全校验失败 | path=%s 不满足前缀=%s", path, safe_prefix)
        return JSONResponse(status_code=403, content={"error": "Access denied"})

    logger.info("DELETE 安全校验通过 | path=%s", path)

    if os.path.isdir(path):
        logger.info("DELETE 目标为目录 | path=%s", path)
        try:
            os.rmdir(path)
            logger.info("DELETE 目录已删除 | path=%s", path)
        except OSError as e:
            logger.error("DELETE 目录删除失败 | path=%s error=%s", path, e)
            return JSONResponse(status_code=400, content={"error": f"Directory not empty or cannot delete: {e}"})
        return {"status": "deleted", "source": path, "wiki_pages_deleted": 0}

    if not os.path.isfile(path):
        logger.warning("DELETE 文件不存在 | path=%s cwd=%s", path, os.getcwd())
        return JSONResponse(status_code=404, content={"error": "File not found", "path": path})

    logger.info("DELETE 目标为文件 | path=%s", path)
    wiki_deleted = _cascade_delete_wiki(path)
    os.remove(path)
    logger.info("DELETE 文件已删除 | path=%s wiki_deleted=%d", path, wiki_deleted)

    return {"status": "deleted", "source": path, "wiki_pages_deleted": wiki_deleted}


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
