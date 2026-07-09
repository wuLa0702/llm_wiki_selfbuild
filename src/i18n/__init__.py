"""
国际化（i18n） — YAML 配置驱动的翻译系统

用法：
    from src.i18n import _
    print(_("wiki.stats.total", count=42))
    print(_("wiki.nav.home"))
"""
import os
import logging
from pathlib import Path

import yaml

from src.config import settings

logger = logging.getLogger("i18n")

# 翻译缓存 {lang: {key: value}}
_translations: dict[str, dict] = {}
_loaded_lang: str | None = None
_current: dict = {}


def _load_yaml(lang: str) -> dict:
    """加载指定语言的 YAML 翻译文件"""
    i18n_dir = Path(os.path.dirname(__file__))
    file_path = i18n_dir / f"{lang}.yaml"

    if not file_path.exists():
        logger.warning("翻译文件不存在 | lang=%s path=%s", lang, file_path)
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            _translations[lang] = data or {}
            return _translations[lang]
    except Exception as exc:
        logger.warning("翻译文件加载失败 | lang=%s error=%s", lang, exc)
        return {}


def _ensure_loaded() -> dict:
    """确保当前语言的翻译已加载"""
    lang = settings.output_language or "zh"
    global _current, _loaded_lang
    if lang != _loaded_lang:
        data = _load_yaml(lang)
        # 补全：如果 key 缺失，用中文兜底
        if lang != "zh":
            zh = _translations.get("zh") or _load_yaml("zh")
            _current = {**zh, **data}  # en 覆盖 zh
        else:
            _current = data
        _loaded_lang = lang
    return _current


def _resolve_key(data: dict, key: str) -> str | None:
    """递归解析点分隔的 key

    >>> _resolve_key({"a": {"b": "hello"}}, "a.b")
    'hello'
    """
    keys = key.split(".")
    value = data
    for k in keys:
        if isinstance(value, dict):
            value = value.get(k)
        else:
            return None
    return value if isinstance(value, str) else None


def gettext(key: str, **kwargs) -> str:
    """获取翻译文本

    Args:
        key: 点分隔的翻译 key，如 "wiki.nav.home"
        **kwargs: 格式化参数，如 count=42

    Returns:
        翻译后的文本。key 不存在时返回 key 本身（不崩溃）。
    """
    try:
        data = _ensure_loaded()
        value = _resolve_key(data, key)
        if value is None:
            return key
        if kwargs:
            return value.format(**kwargs)
        return value
    except Exception:
        logger.debug("翻译查询失败 | key=%s", key, exc_info=True)
        return key


# 快捷别名
_ = gettext
