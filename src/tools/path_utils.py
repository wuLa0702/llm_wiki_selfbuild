"""
路径安全工具 — 路径前缀校验、穿越防御
"""
import os


def safe_path(base_dir: str, user_path: str) -> str:
    """
    安全拼接路径，防止 ../ 穿越攻击

    Args:
        base_dir: 允许访问的基目录（如 "raw"、"wiki"）
        user_path: 用户/Agent 传入的相对路径

    Returns:
        规范化后的绝对路径

    Raises:
        PermissionError: 绝对路径、路径穿越、越权访问
    """
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
