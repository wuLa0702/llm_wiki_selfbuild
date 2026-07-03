"""
LLM Wiki — FastAPI 服务入口
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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


@app.get("/")
async def root():
    return {"message": "LLM Wiki is running", "version": "0.1.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/ingest")
async def ingest():
    """Ingest a source file into the wiki (to be implemented)"""
    return {"message": "Ingest endpoint — not yet implemented"}


@app.get("/v1/query")
async def query():
    """Query the wiki knowledge base (to be implemented)"""
    return {"message": "Query endpoint — not yet implemented"}


@app.get("/v1/lint")
async def lint():
    """Check wiki health (to be implemented)"""
    return {"message": "Lint endpoint — not yet implemented"}
