"""
Wiki 页面健康检查器 — Phase 3 只做确定性静态检测

所有检测纯确定性算法，零 LLM 调用。
复用 WikiGraph 图数据做断链和孤页判断，直接扫描文件做 index 缺失判断。
"""
import os
import re

from src.core.graph import WikiGraph
from src.core.logging_config import get_logger

logger = get_logger("linter")

# 导航文件 — 孤页检测中跳过
NAV_FILES = {"index.md", "overview.md", "log.md"}


class LintTool:
    """Wiki 页面健康检查器 — 纯静态检测"""

    def __init__(self, wiki_dir: str = "wiki") -> None:
        """
        Args:
            wiki_dir: wiki 目录路径
        """
        self.wiki_dir = wiki_dir
        self._graph: WikiGraph | None = None

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @property
    def graph(self) -> WikiGraph:
        """懒加载 WikiGraph 实例"""
        if self._graph is None:
            self._graph = WikiGraph(wiki_dir=self.wiki_dir)
            self._graph.build()
        return self._graph

    @staticmethod
    def _is_http_link(target: str) -> bool:
        """判断是否为 HTTP/HTTPS 外部链接"""
        return target.startswith("http://") or target.startswith("https://")

    @staticmethod
    def _read_file(path: str) -> str | None:
        """安全读取文件内容，失败返回 None"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("无法读取文件 | path=%s error=%s", path, exc)
            return None

    # ------------------------------------------------------------------
    # 检测1：断链
    # ------------------------------------------------------------------

    def check_broken_links(self) -> list[dict]:
        """
        检测断链：[[target]] 指向不存在的文件

        跳过 HTTP/HTTPS 外部链接。

        Returns:
            [{"source_page": "entities/xxx.md", "broken_target": "entities/nonexistent.md"}]
        """
        g = self.graph
        existing_nodes = set(g.nodes())
        broken: list[dict] = []

        for source, target in g.edges():
            if self._is_http_link(target):
                continue
            # 目标存在于 nodes() 中 → 有效链接
            if target in existing_nodes:
                continue
            broken.append({
                "source_page": source,
                "broken_target": target,
            })

        logger.info("断链检测完成 | count=%d", len(broken))
        return broken

    # ------------------------------------------------------------------
    # 检测2：孤页
    # ------------------------------------------------------------------

    def check_orphan_pages(self) -> list[str]:
        """
        检测孤页：没有任何页面链接到它（0 入链）

        排除 index.md, overview.md, log.md 等导航页面。

        Returns:
            孤页路径列表 ["concepts/forgotten.md", ...]
        """
        g = self.graph
        orphans: list[str] = []

        for node in g.nodes():
            if node in NAV_FILES:
                continue
            deg = g.degree(node)
            if deg["in_degree"] == 0:
                orphans.append(node)

        logger.info("孤页检测完成 | count=%d", len(orphans))
        return orphans

    # ------------------------------------------------------------------
    # 检测3：index 缺失
    # ------------------------------------------------------------------

    def check_index_gaps(self) -> list[str]:
        """
        检测 index.md 中缺失的页面：wiki/ 下存在但 index.md 未列出的页面

        通过扫描 index.md 内容，收集其中出现的所有 wikilinks 路径，
        与全部页面路径对比，找出未在 index 中引用的页面。
        排除 index.md、overview.md、log.md 自身。

        Returns:
            缺失页面路径列表 ["entities/new_page.md", ...]
        """
        index_path = os.path.join(self.wiki_dir, "index.md")
        index_text = self._read_file(index_path)
        if index_text is None:
            logger.info("index.md 不存在，跳过 index 缺口检测")
            return []

        # 收集 index.md 中引用的所有页面路径
        from src.core.graph import WIKILINK_PATTERN as PATTERN

        referenced: set[str] = set()
        for m in PATTERN.finditer(index_text):
            target = m.group(1).strip()
            if not self._is_http_link(target):
                referenced.add(target)

        # 对比所有页面
        g = self.graph
        gaps: list[str] = []
        for node in g.nodes():
            if node in NAV_FILES:
                continue
            if node not in referenced:
                gaps.append(node)

        logger.info("Index 缺口检测完成 | count=%d", len(gaps))
        return sorted(gaps)

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """
        运行全部静态检查

        Returns:
            {
                "broken_links": [...],
                "broken_links_count": 3,
                "orphan_pages": [...],
                "orphan_pages_count": 1,
                "index_gaps": [...],
                "index_gaps_count": 2,
                "health_score": 85,
                "summary": "检测摘要文本"
            }
        """
        broken = self.check_broken_links()
        orphans = self.check_orphan_pages()
        gaps = self.check_index_gaps()

        # 健康评分：100 起，逐项扣分
        score = 100
        score -= len(broken) * 5
        score -= len(orphans) * 10
        score -= len(gaps) * 3
        score = max(0, score)

        # 构建摘要
        parts: list[str] = []
        if broken:
            parts.append(f"断链 {len(broken)} 处")
        if orphans:
            parts.append(f"孤页 {len(orphans)} 个")
        if gaps:
            parts.append(f"index 缺口 {len(gaps)} 个")
        summary = "健康" if score == 100 else f"需关注（{'，'.join(parts)}）" if parts else "健康"

        result = {
            "broken_links": broken,
            "broken_links_count": len(broken),
            "orphan_pages": orphans,
            "orphan_pages_count": len(orphans),
            "index_gaps": gaps,
            "index_gaps_count": len(gaps),
            "health_score": score,
            "summary": f"Wiki 健康评分 {score}/100 · {summary}",
        }

        logger.info("Lint 全部检测完成 | score=%d broken=%d orphans=%d gaps=%d",
                     score, len(broken), len(orphans), len(gaps))
        return result
