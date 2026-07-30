"""
搜索工具 — 在 wiki 目录中搜索内容（文件名 + 全文匹配）

纯确定性算法，不调用 LLM。
"""
import os
import re

from src.core.logging_config import get_logger
from src.utils.path_resolver import get_wiki_dir

logger = get_logger("search")

# 导航文件列表（不计入搜索结果）
NAV_FILES = {"index.md", "overview.md", "log.md"}


class SearchTool:
    """在 wiki 目录中搜索关键词（文件名 + 全文）"""

    def __init__(self, wiki_dir: str | None = None) -> None:
        """
        Args:
            wiki_dir: wiki 根目录的路径，None 或 "wiki" 自动解析到 %APPDATA%
        """
        self.wiki_dir = wiki_dir if wiki_dir and wiki_dir != "wiki" else get_wiki_dir()

    def search(self, keyword: str, limit: int = 15) -> list[dict]:
        """
        遍历 wiki/ 下所有 .md 文件，搜索关键词

        排序策略：文件名匹配 > 标题匹配 > 正文匹配

        Args:
            keyword: 搜索关键词（大小写不敏感）
            limit: 最大返回结果数

        Returns:
            [
                {
                    "path": "entities/xxx.md",
                    "title": "XXX",
                    "snippet": "匹配行上下文...",
                    "match_type": "filename" | "title" | "content"
                },
                ...
            ]
        """
        if not keyword or not keyword.strip():
            return []

        kw = keyword.lower().strip()
        results: list[dict] = []
        seen: set[str] = set()

        if not os.path.isdir(self.wiki_dir):
            logger.warning("wiki 目录不存在 | path=%s", self.wiki_dir)
            return []

        for root, _dirs, files in os.walk(self.wiki_dir):
            for filename in files:
                if not filename.endswith(".md"):
                    continue
                if filename in NAV_FILES:
                    continue

                rel_path = os.path.relpath(os.path.join(root, filename), self.wiki_dir)
                norm_path = rel_path.replace("\\", "/")

                if norm_path in seen:
                    continue

                # 文件名匹配（最高优先级）
                if kw in filename.lower():
                    title = self._extract_title_from_file(
                        os.path.join(root, filename)
                    )
                    results.append({
                        "path": norm_path,
                        "title": title or filename[:-3],
                        "snippet": f"文件名包含 \"{keyword}\"",
                        "match_type": "filename",
                    })
                    seen.add(norm_path)
                    continue

                # 检查文件内容
                file_path = os.path.join(root, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except (OSError, UnicodeDecodeError) as exc:
                    logger.debug("跳过无法读取的文件 | path=%s error=%s", file_path, exc)
                    continue

                # 标题匹配（次优先级）
                title = self._extract_title_from_content(content)
                if title and kw in title.lower():
                    results.append({
                        "path": norm_path,
                        "title": title,
                        "snippet": f"标题包含 \"{keyword}\"",
                        "match_type": "title",
                    })
                    seen.add(norm_path)
                    continue

                # 正文匹配（最低优先级）
                snippet = self._extract_snippet(content, kw)
                if snippet:
                    results.append({
                        "path": norm_path,
                        "title": title or filename[:-3],
                        "snippet": snippet,
                        "match_type": "content",
                    })
                    seen.add(norm_path)

        # 按 match_type 排序：filename > title > content
        priority = {"filename": 0, "title": 1, "content": 2}
        results.sort(key=lambda r: (priority.get(r["match_type"], 9), r["path"]))
        return results[:limit]

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_title_from_file(file_path: str) -> str:
        """从文件读取并提取 Markdown 标题"""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                first_line = f.readline()
                content = first_line
                if first_line.strip().startswith("---"):
                    # frontmatter，跳过
                    for line in f:
                        content = line
                        if line.strip() == "---":
                            content = f.readline()
                            break
                return SearchTool._extract_title_from_content(content)
        except (OSError, UnicodeDecodeError):
            return ""

    @staticmethod
    def _extract_title_from_content(content: str) -> str:
        """从 Markdown 内容提取 # 标题"""
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped[2:].strip()
        return ""

    @staticmethod
    def _extract_snippet(content: str, keyword: str) -> str | None:
        """
        从内容中提取包含关键词的匹配行上下文

        Returns:
            匹配行前后各 30 字符的上下文，或 None 未找到
        """
        kw_lower = keyword.lower()
        for line in content.split("\n"):
            if kw_lower in line.lower():
                stripped = line.strip()
                if not stripped:
                    continue
                # 截断过长行
                idx = stripped.lower().index(kw_lower)
                start = max(0, idx - 30)
                end = min(len(stripped), idx + len(keyword) + 30)
                snippet = stripped[start:end].strip()
                if start > 0:
                    snippet = "..." + snippet
                if end < len(stripped):
                    snippet = snippet + "..."
                return snippet[:120]  # 硬限制 120 字符
        return None
