"""
日志配置模块 — 集中管理项目日志

通过环境变量控制，默认开启（2026-08-01 起）：
  LOG_ENABLED=true     # 开关，默认 true
  LOG_LEVEL=INFO       # DEBUG / INFO / WARNING / ERROR
  LOG_FILE=logs/wiki.log  # 文件路径，默认 logs/wiki.log（相对 CWD）

文件日志双重轮转（TimedRotatingFileHandler）：
  - 按日切片（when="midnight"）
  - 单文件超 100MB 强制切片（maxBytes）
  - 保留 15 天（backupCount=15）
"""
import logging
import logging.handlers
import os
import sys

from dotenv import load_dotenv

from src.utils.path_resolver import get_log_dir

load_dotenv()

LOGGER_NAME = "llm_wiki"
_configured = False

# 文件日志双重轮转默认值：单文件 100MB，保留 15 天
MAX_LOG_BYTES = 100 * 1024 * 1024
LOG_BACKUP_COUNT = 15


class DailySizeRotatingFileHandler(logging.handlers.TimedRotatingFileHandler):
    """按日 + 按大小双重轮转的文件日志 Handler

    - 按日切片：when="midnight"
    - 大小切片：maxBytes 属性在 shouldRollover 中被原生检查，
      超限即触发 rollover（无需重写方法）
    - 保留 LOG_BACKUP_COUNT 份归档（15 天）
    """

    def __init__(self, filename: str, encoding: str = "utf-8") -> None:
        super().__init__(
            filename,
            when="midnight",
            backupCount=LOG_BACKUP_COUNT,
            encoding=encoding,
        )
        self.maxBytes = MAX_LOG_BYTES


def reset_logging() -> None:
    """重置日志配置（仅在测试中使用）"""
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.disabled = False
    _configured = False


def configure_logging() -> None:
    """根据环境变量配置日志系统

    环境变量：
        LOG_ENABLED: 是否启用日志（true/false，默认 true）
        LOG_LEVEL:   日志级别（DEBUG/INFO/WARNING/ERROR，默认 INFO）
        LOG_FILE:    日志文件路径（默认 logs/wiki.log）

    文件日志双重轮转：按日 + 100MB 切片，保留 15 天。

    线程安全：当前为单线程项目，未加锁。
    """
    global _configured

    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    enabled = os.environ.get("LOG_ENABLED", "true").strip().lower() == "true"

    if not enabled:
        # 关闭状态：添加 NullHandler 阻止传播到 root logger
        logger.addHandler(logging.NullHandler())
        logger.disabled = True
        _configured = True
        return

    # 启用状态
    logger.disabled = False
    level_name = os.environ.get("LOG_LEVEL", "INFO").strip().upper()
    level = getattr(logging, level_name, logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台输出
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # 文件输出 — 双重轮转：按日（midnight）+ 100MB + 保留 15 天
    # 默认写入数据目录 logs/wiki.log（与 get_log_dir() 一致，
    # 修复 2026-08-01：LLM_WIKI_DATA_DIR 覆盖时 CWD 相对路径会写错位置）
    log_file = os.environ.get("LOG_FILE", "").strip() or os.path.join(get_log_dir(), "wiki.log")
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = DailySizeRotatingFileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # 图谱调试日志（独立文件，仅在日志启用时有效）
    if os.environ.get("LOG_GRAPH", "false").strip().lower() == "true":
        graph_log_dir = os.environ.get("LOG_GRAPH_DIR", "logs")
        os.makedirs(graph_log_dir, exist_ok=True)
        graph_handler = logging.FileHandler(
            os.path.join(graph_log_dir, "graph.log"), encoding="utf-8",
        )
        graph_handler.setLevel(logging.DEBUG)
        graph_handler.setFormatter(formatter)
        graph_logger = logging.getLogger(f"{LOGGER_NAME}.graph")
        graph_logger.addHandler(graph_handler)
        graph_logger.setLevel(logging.DEBUG)
        main_logger = logging.getLogger(f"{LOGGER_NAME}.main")
        main_logger.addHandler(graph_handler)
        logger.info("图谱调试日志已开启 | dir=%s", graph_log_dir)

    _configured = True


def get_logger(name: str = "") -> logging.Logger:
    """获取项目 Logger

    Args:
        name: 子模块名称，如 "adapter"、"main"

    Returns:
        配置后的 Logger 实例
    """
    if not _configured:
        configure_logging()

    if name:
        return logging.getLogger(f"{LOGGER_NAME}.{name}")
    return logging.getLogger(LOGGER_NAME)
