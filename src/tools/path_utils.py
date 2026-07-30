"""
路径安全工具 — 路径前缀校验、穿越防御

内置已知目录别名自动解析（打包兼容）：
  - "wiki" → get_wiki_dir()（%APPDATA%/LLM-Wiki/wiki）
  - "raw"  → get_raw_dir()（%APPDATA%/LLM-Wiki/raw）
  非别名：保持原值不变（兼容测试传绝对路径）
"""
import os

from src.utils.path_resolver import get_raw_dir, get_wiki_dir


def _resolve_alias(base_dir: str) -> str:
    """解析已知目录别名，非别名返回原值

    运行时调用 resolver，支持 pytest monkeypatch 覆盖测试目录。
    """
    if base_dir == "wiki":
        return get_wiki_dir()
    if base_dir == "raw":
        return get_raw_dir()
    return base_dir


def safe_path(base_dir: str, user_path: str) -> str:
    """
    安全拼接路径，防止 ../ 穿越攻击

    Args:
        base_dir: 允许访问的基目录（如 "raw"、"wiki"），自动解析别名
        user_path: 用户/Agent 传入的相对路径

    Returns:
        规范化后的绝对路径

    Raises:
        PermissionError: 绝对路径、路径穿越、越权访问
    """
    # 解析已知目录别名（打包兼容）
    base_dir = _resolve_alias(base_dir)

    # 拒绝绝对路径
    if os.path.isabs(user_path):
        raise PermissionError(f"Absolute path not allowed: {user_path}")

    # 规范化基准目录和用户路径
    base = os.path.normpath(base_dir)
    full = os.path.normpath(os.path.join(base, user_path))

    # 校验最终路径仍在基准目录之内
    if not full.startswith(base + os.sep) and full != base:
        raise PermissionError(f"Path traversal detected: {user_path}")

    return full
