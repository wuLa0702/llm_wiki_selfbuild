"""路由: 摄入 — /v1/ingest, /v1/ingest/queue/*, /v1/ingest/folder"""
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.app_state import get_ingest_queue, get_task_queue
from src.models.common import FolderImportResponse, QueueActionResponse, QueueProgressResponse
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


@router.post("/v1/ingest/queue/retry/{job_id}", response_model=QueueActionResponse)
async def ingest_queue_retry(job_id: str):
    """重试失败的任务"""
    logger.info("POST /v1/ingest/queue/retry/%s", job_id)
    queue = get_ingest_queue()
    if queue is None:
        return QueueActionResponse(status="error", message="队列未初始化")
    ok = queue.retry(job_id)
    return QueueActionResponse(status="ok" if ok else "not_found", job_id=job_id)


@router.post("/v1/ingest/folder", response_model=FolderImportResponse)
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
        return importer.import_folder_async(folder_path, get_ingest_queue(), recurse=recurse)
    else:
        compiler = WikiCompiler(task_queue=get_task_queue())
        return importer.import_folder(folder_path, recurse=recurse, compiler=compiler)
