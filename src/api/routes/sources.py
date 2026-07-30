"""
路由: 资料来源 — /v1/sources/*
"""
import logging
import os
import re
import shutil
import sqlite3
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.core.logging_config import get_logger
from src.utils.path_resolver import get_db_path, get_raw_sources_dir, get_wiki_dir

logger = get_logger("api.routes.sources")
router = APIRouter(tags=["sources"])


def _safe_base() -> str:
    """返回 raw/sources 的绝对路径（规范化），作为安全校验的基目录"""
    return os.path.normpath(get_raw_sources_dir())


def _resolve_source_path(rel_path: str) -> tuple[str | None, int | None]:
    """将前端传来的路径（如 raw/sources/foo.md）解析为绝对路径，做安全校验。

    Returns:
        (abs_path, None) — 校验通过，返回绝对路径
        (None, status_code) — 校验失败，返回 HTTP 状态码
    """
    # 统一分隔符
    cleaned = rel_path.strip().lstrip("/").replace("\\", "/")

    # 前端传的路径格式是 raw/sources/xxx，去掉前缀
    prefix = "raw/sources/"
    if not cleaned.startswith(prefix) and cleaned != "raw/sources":
        logger.warning("路径安全校验失败: %s (不在 raw/sources/ 下)", cleaned)
        return None, 403

    rel = cleaned[len(prefix):] if cleaned != "raw/sources" else ""
    abs_path = os.path.normpath(os.path.join(_safe_base(), rel))

    # 防御路径穿越：最终路径必须在 safe_base 内
    base = _safe_base()
    if abs_path != base and not abs_path.startswith(base + os.sep):
        logger.warning("路径穿越检测: %s", rel_path)
        return None, 403

    return abs_path, None


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
    entries.sort(key=lambda x: (0 if x[1] == "directory" else 1, x[2] if x[1] == "file" else 0))
    base_prefix = _safe_base()
    for name, typ, data in entries:
        full = os.path.join(base, name)
        # 返回给前端的路径用 raw/sources/xxx 格式（相对 APP_DATA_DIR）
        rel_to_appdata = os.path.relpath(full, os.path.dirname(base_prefix))
        display_path = rel_to_appdata.replace("\\", "/")
        if typ == "directory":
            items.append({"name": name, "type": "directory", "path": display_path, "children": data})
        else:
            items.append({"name": name, "type": "file", "path": display_path, "size": int(os.path.getsize(full))})
    return items


@router.get("/v1/sources/tree")
async def sources_tree():
    """返回 raw/sources/ 的完整目录树"""
    base = _safe_base()
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
    """删除关联的 Wiki 页面（通过 sources frontmatter 匹配），返回删除数"""
    wiki_dir = get_wiki_dir()
    db_file = get_db_path("wiki.db")
    deleted = 0
    source_ref = os.path.basename(source_path).replace("\\", "/")
    source_abs = os.path.normpath(source_path)

    if not os.path.isdir(wiki_dir):
        return 0

    for wiki_file in Path(wiki_dir).rglob("*.md"):
        try:
            content = wiki_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        m = re.search(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not m:
            continue
        frontmatter = m.group(1)
        if source_ref in frontmatter or source_abs.replace("\\", "/") in frontmatter:
            rel_path = str(wiki_file.relative_to(wiki_dir)).replace("\\", "/")
            try:
                wiki_file.unlink()
            except OSError:
                pass
            try:
                conn = sqlite3.connect(db_file)
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
    """删除单个源文件或空目录，级联删除关联 wiki 页面"""
    raw_path = path
    path = path.strip().lstrip("/").replace("\\", "/")
    logger.info("DELETE /v1/sources/delete | raw=%s cleaned=%s", raw_path, path)

    if not path:
        logger.warning("DELETE 拒绝: path 为空 | raw=%s", raw_path)
        return JSONResponse(status_code=400, content={"error": "path is required"})

    abs_path, err = _resolve_source_path(path)
    if err:
        return JSONResponse(status_code=err, content={"error": "Access denied"})

    assert abs_path is not None

    if os.path.isdir(abs_path):
        logger.info("DELETE 目标为目录 | abs=%s", abs_path)
        try:
            os.rmdir(abs_path)
            logger.info("DELETE 目录已删除 | abs=%s", abs_path)
        except OSError as e:
            logger.error("DELETE 目录删除失败 | abs=%s error=%s", abs_path, e)
            return JSONResponse(status_code=400, content={"error": f"Directory not empty or cannot delete: {e}"})
        return {"status": "deleted", "source": path, "wiki_pages_deleted": 0}

    if not os.path.isfile(abs_path):
        logger.warning("DELETE 文件不存在 | abs=%s", abs_path)
        return JSONResponse(status_code=404, content={"error": "File not found", "path": path})

    logger.info("DELETE 目标为文件 | abs=%s", abs_path)
    wiki_deleted = _cascade_delete_wiki(abs_path)
    os.remove(abs_path)
    logger.info("DELETE 文件已删除 | abs=%s wiki_deleted=%d", abs_path, wiki_deleted)

    return {"status": "deleted", "source": path, "wiki_pages_deleted": wiki_deleted}


@router.delete("/v1/sources/folder/{folder_path:path}")
async def delete_source_folder(folder_path: str):
    """级联删除文件夹，级联删除关联 wiki 页面"""
    logger.info("DELETE /v1/sources/folder/%s", folder_path)

    abs_path, err = _resolve_source_path(folder_path)
    if err:
        return JSONResponse(status_code=err, content={"error": "Access denied"})

    assert abs_path is not None

    if not os.path.isdir(abs_path):
        return JSONResponse(status_code=404, content={"error": "Directory not found", "path": folder_path})

    file_paths: list[str] = []
    for root, _, files in os.walk(abs_path):
        for f in files:
            fp = os.path.join(root, f).replace("\\", "/")
            file_paths.append(fp)

    total_wiki_deleted = 0
    for fp in file_paths:
        total_wiki_deleted += _cascade_delete_wiki(fp)

    shutil.rmtree(abs_path)

    return {"status": "deleted", "folder": folder_path, "files_deleted": len(file_paths), "wiki_pages_deleted": total_wiki_deleted}


# =====================================================================
# 提取到 Wiki（异步 Agent）
# =====================================================================

class ExtractRequest(BaseModel):
    source_path: str
    force: bool = False


@router.post("/v1/sources/extract-to-wiki")
async def extract_to_wiki(body: ExtractRequest):
    """大文件 → Agent 多页面提取"""
    source_path = body.source_path
    force = body.force
    logger.info("POST /v1/sources/extract-to-wiki | %s force=%s", source_path, force)

    abs_path, err = _resolve_source_path(source_path)
    if err:
        return JSONResponse(status_code=err, content={"error": "Access denied"})

    assert abs_path is not None

    if not os.path.isfile(abs_path):
        return JSONResponse(status_code=404, content={"error": "File not found", "path": source_path})

    from src.core.compiler import WikiCompiler
    from src.app_state import get_task_queue

    compiler = WikiCompiler(task_queue=get_task_queue())

    # compiler.ingest 接受相对路径（相对 sources_dir），传入相对基目录的路径
    rel = os.path.relpath(abs_path, _safe_base())

    try:
        result = compiler.ingest(rel, force=force)
        return JSONResponse({
            "status": result.get("status", "ok"),
            "message": result.get("message", "提取完成"),
            "pages_created": result.get("pages_created", []),
            "pages_updated": result.get("pages_updated", []),
        })
    except Exception as e:
        logger.error("提取失败: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})


# =====================================================================
# 提取前预检
# =====================================================================

@router.get("/v1/sources/check-changed")
async def check_source_changed(path: str):
    """检查源文件自上次 ingest 后是否变化"""
    logger.info("GET /v1/sources/check-changed | path=%s", path)

    abs_path, err = _resolve_source_path(path)
    if err:
        return JSONResponse(status_code=err, content={"error": "Access denied"})

    assert abs_path is not None

    if not os.path.isfile(abs_path):
        return JSONResponse(status_code=404, content={"error": "File not found"})

    from src.core.cache import IngestCache
    cache = IngestCache()

    rel_path = os.path.relpath(abs_path, _safe_base())
    changed = cache.has_changed(rel_path)
    return {
        "changed": changed,
        "cached": not changed,
        "path": path,
    }


# =====================================================================
# 编辑原始文件
# =====================================================================

class SourceEditRequest(BaseModel):
    path: str
    content: str


@router.post("/v1/sources/edit")
async def edit_source(body: SourceEditRequest):
    """编辑原始资料文件，保存后自动触发 ingest 更新 Wiki"""
    path = body.path.strip()
    logger.info("POST /v1/sources/edit | %s", path)

    abs_path, err = _resolve_source_path(path)
    if err:
        return JSONResponse(status_code=err, content={"error": "Access denied"})

    assert abs_path is not None

    if not os.path.isfile(abs_path):
        return JSONResponse(status_code=404, content={"error": "File not found", "path": path})

    try:
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(body.content)
        logger.info("文件已写入 | abs=%s size=%d", abs_path, len(body.content))
    except OSError as e:
        logger.error("文件写入失败 | abs=%s error=%s", abs_path, e)
        return JSONResponse(status_code=500, content={"error": f"Write failed: {e}"})

    from src.core.compiler import WikiCompiler
    from src.app_state import get_task_queue

    rel_path = os.path.relpath(abs_path, _safe_base())
    compiler = WikiCompiler(task_queue=get_task_queue())

    try:
        result = compiler.ingest(rel_path)
        logger.info(
            "编辑后 ingest 完成 | source=%s created=%d updated=%d",
            path,
            len(result.get("pages_created", [])),
            len(result.get("pages_updated", [])),
        )
        return {
            "status": "ok",
            "pages_created": result.get("pages_created", []),
            "pages_updated": result.get("pages_updated", []),
            "message": f"已更新: {len(result.get('pages_created', []))} 创建, {len(result.get('pages_updated', []))} 更新",
        }
    except Exception as e:
        logger.error("编辑后 ingest 失败 | source=%s error=%s", path, e)
        return JSONResponse(status_code=500, content={"error": f"Ingest failed: {e}"})
