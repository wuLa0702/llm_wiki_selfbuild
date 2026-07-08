"""
日志配置模块单元测试
"""
import logging
import os

import pytest

from src.core.logging_config import (
    LOGGER_NAME,
    configure_logging,
    get_logger,
    reset_logging,
)


@pytest.fixture(autouse=True)
def reset_logging_after():
    """每个测试后重置日志配置，避免测试间相互影响"""
    yield
    reset_logging()


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------


def test_get_logger_returns_correct_name():
    """get_logger 返回正确命名的子 Logger"""
    logger = get_logger("adapter")
    assert logger.name == f"{LOGGER_NAME}.adapter"


def test_get_logger_root():
    """不传 name 时返回根 Logger"""
    logger = get_logger()
    assert logger.name == LOGGER_NAME


def test_logger_disabled_by_default(mocker):
    """默认状态下（无环境变量）logger 处于禁用状态"""
    mocker.patch.dict(os.environ, {}, clear=True)
    reset_logging()
    configure_logging()
    logger = get_logger()
    assert logger.disabled is True


def test_logger_enabled_when_env_set(mocker):
    """LOG_ENABLED=true 时 logger 处于启用状态"""
    mocker.patch.dict(os.environ, {"LOG_ENABLED": "true"})
    configure_logging()

    logger = get_logger()
    assert logger.disabled is False


def test_logger_has_handlers_when_enabled(mocker):
    """LOG_ENABLED=true 时 logger 添加了至少一个处理器"""
    mocker.patch.dict(os.environ, {"LOG_ENABLED": "true"})
    configure_logging()

    logger = get_logger()
    assert len(logger.handlers) > 0


def test_logger_file_handler_when_log_file_set(mocker, tmp_path):
    """LOG_FILE 设置时，文件处理器被添加"""
    log_file = str(tmp_path / "test.log")
    mocker.patch.dict(
        os.environ,
        {"LOG_ENABLED": "true", "LOG_FILE": log_file},
    )
    configure_logging()

    logger = get_logger()
    file_handlers = [
        h for h in logger.handlers if isinstance(h, logging.FileHandler)
    ]
    assert len(file_handlers) == 1
    assert file_handlers[0].baseFilename == os.path.abspath(log_file)


# ---------------------------------------------------------------------------
# 边界条件
# ---------------------------------------------------------------------------


def test_log_level_respected(mocker):
    """LOG_LEVEL=WARNING 时处理器只接收 WARNING+ 级别的日志"""
    mocker.patch.dict(os.environ, {"LOG_ENABLED": "true", "LOG_LEVEL": "WARNING"})
    configure_logging()

    root = logging.getLogger(LOGGER_NAME)

    # 验证控制台处理器的 level 被正确设置
    console_handlers = [
        h for h in root.handlers if isinstance(h, logging.StreamHandler)
    ]
    assert len(console_handlers) > 0
    assert console_handlers[0].level == logging.WARNING


def test_log_file_created(mocker, tmp_path):
    """LOG_FILE 设置且启用日志时，文件被创建"""
    log_file = str(tmp_path / "wiki.log")
    mocker.patch.dict(
        os.environ,
        {"LOG_ENABLED": "true", "LOG_FILE": log_file},
    )
    configure_logging()

    logger = get_logger("test")
    logger.info("write something")

    assert os.path.exists(log_file)
    content = open(log_file, encoding="utf-8").read()
    assert "write something" in content


# ---------------------------------------------------------------------------
# 错误路径 / 异常情况
# ---------------------------------------------------------------------------


def test_logger_does_not_propagate_to_root_when_disabled():
    """关闭时日志不传播到 root logger 产生意外输出"""
    configure_logging()
    logger = get_logger("test")

    # 清除模块 logger 的所有处理器
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    logger.disabled = True

    # 获取 root logger 的处理器数量快照
    root_handlers_before = len(logging.getLogger().handlers)

    # 这条日志不应该出现在任何地方
    logger.info("this should not appear")

    root_handlers_after = len(logging.getLogger().handlers)
    assert root_handlers_before == root_handlers_after


def test_invalid_log_level_falls_back_to_info(mocker):
    """无效 LOG_LEVEL 值回退到 INFO"""
    mocker.patch.dict(
        os.environ,
        {"LOG_ENABLED": "true", "LOG_LEVEL": "INVALID_LEVEL"},
    )
    # 不应抛出异常
    configure_logging()

    logger = get_logger()
    assert logger.disabled is False


def test_get_logger_multiple_calls_same_instance():
    """多次 get_logger 返回同一个 Logger 实例"""
    logger1 = get_logger("test")
    logger2 = get_logger("test")
    assert logger1 is logger2


def test_log_file_directory_auto_created(mocker, tmp_path):
    """LOG_FILE 目录不存在时自动创建"""
    log_file = str(tmp_path / "logs" / "subdir" / "wiki.log")
    mocker.patch.dict(
        os.environ,
        {"LOG_ENABLED": "true", "LOG_FILE": log_file},
    )
    configure_logging()

    logger = get_logger("test")
    logger.info("test auto-create dir")

    assert os.path.exists(log_file)
