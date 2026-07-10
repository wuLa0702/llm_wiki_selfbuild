"""
应用配置管理 — Pydantic BaseSettings

从 .env 和环境变量读取配置，提供集中式配置访问接口。
"""
import os

from fastapi.templating import Jinja2Templates
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """全局限配置，所有模块从此读取"""

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-v4-flash"

    # 豆包 / 火山引擎 Ark
    ark_api_key: str = ""
    ark_api_base: str = "https://ark.cn-beijing.volces.com/api/v3"
    ark_model_chat: str = "ep-20260704205018-srlpk"
    ark_model_vision: str = "ep-20260704205018-srlpk"
    ark_model_seed2: str = "ep-20260704205835-vbkmb"

    # LLM Provider 选择
    llm_provider: str = "deepseek"

    # 数据库
    wiki_db_path: str = "wiki.db"

    # Wiki 根目录
    wiki_root: str = "."

    # 日志
    log_enabled: bool = True
    log_level: str = "INFO"
    log_file: str = "logs/wiki.log"
    log_graph: bool = False
    log_graph_dir: str = "logs"

    # Source 自动监听
    watcher_enabled: bool = False

    # 语言（zh / en）
    output_language: str = "zh"

    # 调试
    debug_max_chars: int = 0

    # Embedding 向量搜索（sentence-transformers 本地模型）
    embedding_enabled: bool = False
    chroma_persist_dir: str = "chroma_db"
    embedding_model_path: str = ".models/all-MiniLM-L6-v2"

    # MCP Server
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8010

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


settings = Settings()

# Jinja2 模板引擎（路由 / config 共享同一实例）
# 打包模式下从 LLM_WIKI_RESOURCE_DIR 读取资源
_tpl_dir = os.environ.get("LLM_WIKI_RESOURCE_DIR", ".")
_tpl_path = os.path.join(_tpl_dir, "src/api/templates") if os.environ.get("LLM_WIKI_RESOURCE_DIR") else "src/api/templates"
templates = Jinja2Templates(directory=_tpl_path)
