"""
应用级路径解析 — PyInstaller 打包 + 开发模式的统一路径入口

职责：
  - get_app_dir()    → 用户数据目录（持久化，跨版本保留）
  - get_exe_dir()    → exe 内部资源目录（只读）/ 开发模式 CWD
  - get_log_dir()    → 日志目录
  - get_db_path()    → SQLite 持久化数据库路径
  - get_wiki_dir()   → 用户 wiki 知识库目录
  - get_raw_dir()    → 用户原始素材目录
  - get_static_dir() → 静态资源目录

路径规则：
  开发模式：所有路径相对 CWD（行为不变）
  打包模式：数据 → %APPDATA%/LLM-Wiki/，资源 → sys._MEIPASS/
"""
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("path_resolver")

# ── 应用标识 ──────────────────────────────────────────────────────────────────
APP_NAME = "LLM-Wiki"
APP_DATA_DIR = os.environ.get(
    "LLM_WIKI_DATA_DIR",  # 环境变量可覆盖，方便测试
    os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME),
)


def is_frozen() -> bool:
    """判断是否在 PyInstaller 打包环境中运行"""
    return getattr(sys, "frozen", False)


def get_exe_dir() -> str:
    """exe 内部资源目录（只读），开发模式返回 CWD

    PyInstaller 打包后，资源文件解压到 sys._MEIPASS，
    此目录是只读的（下次启动重新解压），不能写入持久数据。
    """
    if is_frozen():
        return str(Path(sys._MEIPASS))
    return str(Path.cwd())


def get_app_dir() -> str:
    """用户数据目录（持久化，跨版本保留）

    存储：
      - agent_persistence.db（对话记忆）
      - wiki/（用户知识库）
      - raw/（用户素材）
      - config.yaml（API Key 等配置）
      - logs/

    路径：%APPDATA%/LLM-Wiki/
    环境变量覆盖：LLM_WIKI_DATA_DIR
    """
    path = APP_DATA_DIR
    os.makedirs(path, exist_ok=True)
    logger.debug("用户数据目录 | path=%s", path)
    return path


def get_log_dir() -> str:
    """日志目录"""
    path = os.path.join(get_app_dir(), "logs")
    os.makedirs(path, exist_ok=True)
    return path


def get_db_path(db_name: str = "agent_persistence.db") -> str:
    """SQLite 数据库的完整路径

    Args:
        db_name: 数据库文件名，默认 agent_persistence.db

    Returns:
        数据库文件的绝对路径
    """
    return os.path.join(get_app_dir(), db_name)


def get_wiki_dir() -> str:
    """Wiki 知识库目录

    用户积累的 Wiki 页面存放于此，跨版本持久化。

    Returns:
        wiki 目录的绝对路径
    """
    path = os.path.join(get_app_dir(), "wiki")
    os.makedirs(path, exist_ok=True)
    return path


def get_raw_dir() -> str:
    """原始素材目录

    用户导入的原始素材存放于此。

    Returns:
        raw 目录的绝对路径
    """
    path = os.path.join(get_app_dir(), "raw")
    os.makedirs(path, exist_ok=True)
    return path


def get_raw_sources_dir() -> str:
    """raw/sources 目录的绝对路径

    用户上传的源文件存放于此，跨版本持久化。

    Returns:
        raw/sources 目录的绝对路径
    """
    path = os.path.join(get_raw_dir(), "sources")
    os.makedirs(path, exist_ok=True)
    return path


def get_static_dir() -> str:
    """静态资源目录

    开发模式：项目根目录下的 static/
    打包模式：exe 内部的 static/（只读）

    Returns:
        static 目录的绝对路径
    """
    base = get_exe_dir() if is_frozen() else Path.cwd()
    return str(Path(base) / "static")


def get_frontend_dist_dir() -> str | None:
    """前端构建产物目录（dist/）

    存在则返回绝对路径，不存在返回 None。
    打包模式下从 exe 内部读取。

    Returns:
        dist 目录的绝对路径，或 None（未构建）
    """
    base = get_exe_dir() if is_frozen() else Path.cwd()
    dist_path = Path(base) / "wiki-ui-v2" / "dist"
    if dist_path.is_dir():
        return str(dist_path)
    return None
