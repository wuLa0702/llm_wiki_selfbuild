"""
配置管理 — config.yaml 持久化读写

职责：
  - 在 %APPDATA%/LLM-Wiki/config.yaml 中持久化用户配置
  - 提供 get/set API 供运行时读取修改
  - 在 app 启动时将 config 中的 API Key 注入环境变量（兼容现有 os.environ 读取）

配置项：
  DEEPSEEK_API_KEY    — DeepSeek API 密钥
  DEEPSEEK_API_BASE   — DeepSeek API 地址
  DEEPSEEK_MODEL      — DeepSeek 模型名
  ARK_API_KEY         — 豆包/火山引擎 API 密钥
  LLM_PROVIDER        — 当前选择的 LLM 提供商（deepseek / doubao）
  OUTPUT_LANGUAGE     — 输出语言（zh / en）
"""
import logging
import os
from pathlib import Path
from typing import Any

import yaml

from src.utils.path_resolver import get_app_dir

logger = logging.getLogger("config_manager")

CONFIG_FILENAME = "config.yaml"

# 已知 API Key 环境变量（启动时从 config 注入到 os.environ）
API_KEY_ENV_VARS = {
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_API_BASE",
    "DEEPSEEK_MODEL",
    "ARK_API_KEY",
    "ARK_API_BASE",
    "ARK_MODEL_CHAT",
}

# 默认配置
DEFAULT_CONFIG: dict[str, Any] = {
    "DEEPSEEK_API_KEY": "",
    "DEEPSEEK_API_BASE": "https://api.deepseek.com/v1",
    "DEEPSEEK_MODEL": "deepseek-v4-flash",
    "LLM_PROVIDER": "deepseek",
    "OUTPUT_LANGUAGE": "zh",
}


def _get_config_path() -> str:
    """获取 config.yaml 的完整路径"""
    return str(Path(get_app_dir()) / CONFIG_FILENAME)


def load_config() -> dict[str, Any]:
    """从 config.yaml 读取配置，不存在时返回默认值

    Returns:
        完整配置字典（含默认值）
    """
    config_path = _get_config_path()
    config = dict(DEFAULT_CONFIG)

    if not os.path.isfile(config_path):
        logger.info("配置文件不存在，使用默认配置 | path=%s", config_path)
        return config

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
        config.update(loaded)
        logger.debug("配置加载完成 | path=%s", config_path)
    except Exception as e:
        logger.warning("配置加载失败，使用默认配置 | error=%s", e)

    return config


def save_config(config: dict[str, Any]) -> None:
    """保存配置到 config.yaml

    Args:
        config: 要保存的配置字典（会合并到现有配置上）
    """
    config_path = _get_config_path()

    # 读取现有配置做合并（避免覆盖未传入的字段）
    existing = {}
    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing = yaml.safe_load(f) or {}
        except Exception:
            existing = {}

    merged = {**DEFAULT_CONFIG, **existing, **config}

    # 过滤掉空值，保留已知键
    clean = {k: v for k, v in merged.items() if k in DEFAULT_CONFIG or k in API_KEY_ENV_VARS}

    try:
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(clean, f, allow_unicode=True, default_flow_style=False)
        logger.info("配置已保存 | path=%s", config_path)
    except Exception as e:
        logger.error("配置保存失败 | error=%s", e)
        raise


def get_config(key: str) -> Any:
    """获取单个配置项

    Args:
        key: 配置键名（如 "DEEPSEEK_API_KEY"）

    Returns:
        配置值，不存在时返回 None
    """
    cfg = load_config()
    return cfg.get(key)


def set_config(key: str, value: Any) -> None:
    """设置单个配置项并持久化

    Args:
        key: 配置键名
        value: 配置值
    """
    save_config({key: value})


def inject_config_to_env() -> None:
    """将 config.yaml 中的 API Key 注入到环境变量

    在 app 启动时调用，使现有 os.environ.get("DEEPSEEK_API_KEY") 读取生效。
    不覆盖已存在的环境变量（开发模式 .env 优先级更高）。
    """
    config = load_config()
    injected = 0
    for key in API_KEY_ENV_VARS:
        value = config.get(key)
        if value and key not in os.environ:
            os.environ[key] = str(value)
            injected += 1

    if injected:
        logger.info("从 config.yaml 注入 %d 个环境变量", injected)


def is_configured() -> bool:
    """检查是否已配置 API Key

    Returns:
        True 表示至少一个 API Key 已配置
    """
    config = load_config()
    return bool(config.get("DEEPSEEK_API_KEY")) or bool(config.get("ARK_API_KEY"))
