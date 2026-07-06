"""
LLM Wiki — FastAPI 服务入口
"""
import os
import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from src.core.logging_config import configure_logging, get_logger
from src.core.models import IngestRequest, IngestResponse
from src.core.privacy import PrivacyManager
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


