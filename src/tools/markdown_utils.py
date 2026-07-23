"""
Markdown 工具函数 — frontmatter 剥离、标题提取等

集中管理 wiki Markdown 文件的通用解析逻辑，避免各处重复实现。
"""
from __future__ import annotations


def strip_frontmatter(content: str) -> str:
    """去掉 Markdown 文件的 YAML frontmatter，返回正文

    Args:
        content: 完整的 Markdown 文件内容（可能含 --- 包裹的 frontmatter）

    Returns:
        去掉 frontmatter 后的正文；若无 frontmatter 则原样返回
    """
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3:].strip()
    return content


def extract_title(content: str) -> str:
    """从 Markdown 内容提取第一个 H1 标题

    Args:
        content: Markdown 文本（可含 frontmatter）

    Returns:
        第一个 # 标题的文本，无标题时返回空字符串
    """
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return ""
