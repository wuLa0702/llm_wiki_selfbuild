"""
日志配置模块 — 集中管理项目日志

通过环境变量控制，默认关闭：
  LOG_ENABLED=false    # 开关
  LOG_LEVEL=INFO       # DEBUG / INFO / WARNING / ERROR
  LOG_FILE=            # 可选文件路径，空则只输出控制台
"""
import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

LOGGER_NAME = "llm_wiki"
_configured = False


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
        LOG_ENABLED: 是否启用日志（true/false，默认 false）
        LOG_LEVEL:   日志级别（DEBUG/INFO/WARNING/ERROR，默认 INFO）
        LOG_FILE:    日志文件路径（可选，不设置只输出控制台）

    线程安全：当前为单线程项目，未加锁。
    """
    global _configured

    logger = logging.getLogger(LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(logging.DEBUG)

    enabled = os.environ.get("LOG_ENABLED", "false").strip().lower() == "true"

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

    # 可选文件输出
    log_file = os.environ.get("LOG_FILE", "").strip()
    if log_file:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
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
