"""路由: 摄入 — /v1/ingest, /v1/ingest/queue/*, /v1/ingest/folder"""
import logging
import os

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.app_state import get_ingest_queue, get_task_queue
from src.models.common import FolderImportAsyncResponse, FolderImportResponse, QueueActionResponse, QueueProgressResponse
from src.models.ingest import IngestRequest, IngestResponse
from src.core.compiler import CompilerError, WikiCompiler
from src.llm.adapter import LLMError

logger = logging.getLogger("api.routes.ingest")
router = APIRouter(tags=["ingest"])


@router.post("/v1/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest):
    """Ingest 一个源文件到 Wiki 知识库"""
    logger.info("POST /v1/ingest | source_path=%s", request.source_path)

    compiler = WikiCompiler(task_queue=get_task_queue())
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


@router.get("/v1/ingest/queue/status", response_model=QueueProgressResponse)
async def ingest_queue_status():
    """查询摄入队列状态"""
    logger.info("GET /v1/ingest/queue/status")
    queue = get_ingest_queue()
    if queue is None:
        return QueueProgressResponse(message="队列未初始化")
    return queue.progress()


@router.post("/v1/ingest/queue/cancel/{job_id}", response_model=QueueActionResponse)
async def ingest_queue_cancel(job_id: str):
    """取消待处理的任务"""
    logger.info("POST /v1/ingest/queue/cancel/%s", job_id)
    queue = get_ingest_queue()
    if queue is None:
        return QueueActionResponse(status="error", message="队列未初始化")
    ok = queue.cancel(job_id)
    return QueueActionResponse(status="ok" if ok else "not_found", job_id=job_id)


@router.get("/v1/ingest/queue/failed")
async def ingest_queue_failed():
    """列出所有失败的任务"""
    queue = get_ingest_queue()
    if queue is None:
        return {"jobs": [], "total": 0}
    jobs = queue.list_failed()
    return {"jobs": jobs, "total": len(jobs)}


@router.get("/v1/ingest/queue/recent")
async def ingest_queue_recent(limit: int = 20):
    """列出最近的任务（含所有状态）"""
    queue = get_ingest_queue()
    if queue is None:
        return {"jobs": [], "total": 0}
    jobs = queue.list_recent(limit=limit)
    return {"jobs": jobs, "total": len(jobs)}


@router.get("/v1/ingest/queue/active")
async def ingest_queue_active():
    """列出活跃任务（pending + processing）"""
    queue = get_ingest_queue()
    if queue is None:
        return {"jobs": [], "total": 0}
    jobs = queue.list_active()
    return {"jobs": jobs, "total": len(jobs)}


@router.delete("/v1/ingest/queue/failed")
async def ingest_queue_clear_failed():
    """清空所有失败任务"""
    queue = get_ingest_queue()
    if queue is None:
        return {"status": "error", "deleted": 0}
    deleted = queue.clear_failed()
    return {"status": "ok", "deleted": deleted}


@router.delete("/v1/ingest/queue/all")
async def ingest_queue_clear_all():
    """清空所有任务记录"""
    queue = get_ingest_queue()
    if queue is None:
        return {"status": "error", "deleted": 0}
    deleted = queue.clear_all()
    return {"status": "ok", "deleted": deleted}


@router.delete("/v1/ingest/queue/{job_id}")
async def ingest_queue_delete(job_id: str):
    """删除任意状态的任务记录"""
    queue = get_ingest_queue()
    if queue is None:
        return {"status": "error", "message": "队列未初始化"}
    ok = queue.delete_job(job_id)
    return {"status": "ok" if ok else "not_found", "job_id": job_id}


@router.post("/v1/ingest/queue/retry/{job_id}", response_model=QueueActionResponse)
async def ingest_queue_retry(job_id: str):
    """重试失败的任务"""
    logger.info("POST /v1/ingest/queue/retry/%s", job_id)
    queue = get_ingest_queue()
    if queue is None:
        return QueueActionResponse(status="error", message="队列未初始化")
    ok = queue.retry(job_id)
    return QueueActionResponse(status="ok" if ok else "not_found", job_id=job_id)


@router.post("/v1/ingest/folder")
async def ingest_folder(request: Request):
    """批量导入文件夹

    body:
        folder_path: 文件夹路径（相对于 raw/sources/）
        recurse: 是否递归子目录（默认 true）
        mode: "sync"（同步）或 "async"（异步，加入队列）
    """
    body = await request.json()
    folder_path = body.get("folder_path", "").strip()
    if not folder_path:
        return JSONResponse(status_code=400, content={"error": "folder_path is required"})

    recurse = body.get("recurse", True)
    mode = body.get("mode", "sync")

    from src.core.ingest import FolderImporter

    importer = FolderImporter()

    if mode == "async":
        # async 模式返回 enqueued 而非 success/created
        result = importer.import_folder_async(folder_path, get_ingest_queue(), recurse=recurse)
        return JSONResponse(content=result)
    else:
        compiler = WikiCompiler(task_queue=get_task_queue())
        return importer.import_folder(folder_path, recurse=recurse, compiler=compiler)


@router.post("/v1/ingest/upload")
async def ingest_upload(request: Request):
    """上传文件到 raw/sources/ 并异步导入"""
    import shutil, traceback

    try:
        form = await request.form()
    except Exception as e:
        return JSONResponse(status_code=400, content={"error": f"Form parse: {type(e).__name__}: {e}"})

    saved = 0
    for val in form.values():
        if not hasattr(val, "read"):
            continue
        filename = getattr(val, "filename", None) or getattr(val, "name", None) or f"upload_{saved}.md"
        safe_path = os.path.normpath(filename)
        if safe_path.startswith("..") or safe_path.startswith("/"):
            continue
        from src.utils.path_resolver import get_raw_sources_dir
        full_path = os.path.join(get_raw_sources_dir(), safe_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        try:
            content = await val.read()
            with open(full_path, "wb") as fh:
                fh.write(content)
            saved += 1
        except Exception as e:
            logger.error("保存上传文件失败 | path=%s error=%s", safe_path, e)

    if saved == 0:
        return JSONResponse(content={"saved": 0, "message": "没有文件被保存"})

    # 异步导入
    queue = get_ingest_queue()
    if queue is None:
        return JSONResponse(status_code=503, content={"saved": saved, "error": "Queue not ready", "detail": "init_services() may not have completed"})
    from src.core.ingest import FolderImporter
    importer = FolderImporter()
    result = importer.import_folder_async(".", queue, recurse=True)
    return JSONResponse(content={
        "saved": saved,
        "total": result.get("total", 0),
        "enqueued": result.get("enqueued", 0),
    })
