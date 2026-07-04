"""
LLM Wiki — FastAPI 服务入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.core.logging_config import configure_logging, get_logger

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


@app.post("/v1/ingest")
async def ingest():
    """Ingest a source file into the wiki (to be implemented)"""
    logger.info("POST /v1/ingest 被调用（桩代码）")
    return {"message": "Ingest endpoint — not yet implemented"}


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
