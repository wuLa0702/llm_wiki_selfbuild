"""
Wiki 页面关系图 — 纯确定性算法解析 [[wikilinks]]

通过正则解析 Markdown 中的双向链接，构建有向图。
零 LLM 调用，1000 页以内 < 100ms。
"""
import os
import re
from collections import defaultdict

from src.core.logging_config import get_logger

logger = get_logger("graph")

# ---------------------------------------------------------------------------
# Wikilinks 正则模式
# ---------------------------------------------------------------------------
# 匹配 [[target]] 和 [[target|display_name]]
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]+)?\]\]")

# 导航文件（不计入图节点）
NAV_FILES = {"index.md", "overview.md", "log.md"}


def parse_wikilinks(content: str) -> list[str]:
    """
    从 Markdown 文本中提取所有 [[wikilinks]] 目标路径

    Args:
        content: Markdown 文本

    Returns:
        wikilink 目标路径列表（去重，保持首次出现顺序）
    """
    seen: set[str] = set()
    result: list[str] = []
    for m in WIKILINK_PATTERN.finditer(content):
        target = m.group(1).strip()
        if target and target not in seen:
            seen.add(target)
            result.append(target)
    return result


class WikiGraph:
    """Wiki 页面的有向图结构（邻接表 + 反链索引）"""

    def __init__(self, wiki_dir: str = "wiki") -> None:
        """
        Args:
            wiki_dir: wiki 目录路径
        """
        self.wiki_dir = wiki_dir
        self._adj: dict[str, list[str]] = {}       # source → [targets]
        self._backlinks: dict[str, list[str]] = {}  # target → [sources]
        self._in_degree: dict[str, int] = {}
        self._out_degree: dict[str, int] = {}
        self._built = False

    # ------------------------------------------------------------------
    # 构建
    # ------------------------------------------------------------------

    def build(self) -> None:
        """
        遍历 wiki/ 下所有 .md 文件 → 解析 wikilinks → 构建邻接表

        跳过 index.md, overview.md, log.md 等导航文件（不建节点，
        但它们的链接关系仍被解析以避免断链误报）。
        """
        self._adj.clear()
        self._backlinks.clear()
        self._in_degree.clear()
        self._out_degree.clear()

        if not os.path.isdir(self.wiki_dir):
            logger.warning("Wiki 目录不存在，跳过图构建 | path=%s", self.wiki_dir)
            self._built = True
            return

        # 第一遍：收集所有文件路径
        all_files: set[str] = set()
        for root, _dirs, files in os.walk(self.wiki_dir):
            for filename in files:
                if not filename.endswith(".md"):
                    continue
                rel = os.path.relpath(os.path.join(root, filename), self.wiki_dir)
                norm = rel.replace("\\", "/")
                all_files.add(norm)

        # 为所有已知页面初始化出度列表
        for f in all_files:
            self._adj.setdefault(f, [])

        # 第二遍：解析每个文件的 wikilinks
        for root, _dirs, files in os.walk(self.wiki_dir):
            for filename in files:
                if not filename.endswith(".md"):
                    continue
                rel = os.path.relpath(os.path.join(root, filename), self.wiki_dir)
                source = rel.replace("\\", "/")

                file_path = os.path.join(root, filename)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except (OSError, UnicodeDecodeError) as exc:
                    logger.debug("跳过无法读取的文件 | path=%s error=%s", file_path, exc)
                    continue

                targets = parse_wikilinks(content)
                self._adj[source] = targets

                for target in targets:
                    self._backlinks.setdefault(target, []).append(source)

        # 统计出入度
        for node in self._adj:
            self._out_degree[node] = len(self._adj[node])
        all_targets = set()
        for targets in self._adj.values():
            all_targets.update(targets)
        for target in all_targets:
            self._in_degree[target] = len(self._backlinks.get(target, []))

        self._built = True
        logger.info("WikiGraph 构建完成 | nodes=%d edges=%d",
                     len(self._adj), sum(len(v) for v in self._adj.values()))

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def nodes(self) -> list[str]:
        """返回所有节点（页面路径），排序"""
        if not self._built:
            self.build()
        return sorted(self._adj.keys())

    def edges(self) -> list[tuple[str, str]]:
        """返回所有有向边 (source → target)"""
        if not self._built:
            self.build()
        result: list[tuple[str, str]] = []
        for source, targets in self._adj.items():
            for target in targets:
                result.append((source, target))
        return result

    def neighbors(self, path: str, depth: int = 1) -> list[str]:
        """
        返回指定路径 depth 跳内的邻居页面（BFS）

        Args:
            path: 页面路径
            depth: BFS 深度（默认 1）

        Returns:
            邻居路径列表（去重，按 BFS 访问顺序）
        """
        if not self._built:
            self.build()

        visited: set[str] = {path}
        queue: list[tuple[str, int]] = [(path, 0)]
        result: list[str] = []

        while queue:
            current, d = queue.pop(0)
            if d >= depth:
                continue

            for neighbor in self._adj.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    result.append(neighbor)
                    queue.append((neighbor, d + 1))

            # 也检查反向链接
            for neighbor in self._backlinks.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    result.append(neighbor)
                    queue.append((neighbor, d + 1))

        return result

    def backlinks(self, path: str) -> list[str]:
        """返回反向链接（哪些页面指向了 path）"""
        if not self._built:
            self.build()
        return self._backlinks.get(path, [])

    def degree(self, path: str) -> dict:
        """
        返回节点的出入度

        Args:
            path: 页面路径

        Returns:
            {"in_degree": N, "out_degree": N}，节点不存在时返回 0/0
        """
        if not self._built:
            self.build()
        return {
            "in_degree": self._in_degree.get(path, 0),
            "out_degree": self._out_degree.get(path, 0),
        }

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """
        返回图数据的 JSON 友好结构，供 API 使用

        Returns:
            {
                "nodes": [
                    {"id": "entities/python.md", "degree": {"in": 2, "out": 3}},
                    ...
                ],
                "edges": [
                    {"source": "entities/python.md", "target": "concepts/ai.md"},
                    ...
                ],
                "stats": {
                    "total_nodes": 10,
                    "total_edges": 15,
                    "avg_degree": 3.0,
                }
            }
        """
        if not self._built:
            self.build()

        nodes_list = []
        for node in self.nodes():
            deg = self.degree(node)
            nodes_list.append({
                "id": node,
                "degree": {"in": deg["in_degree"], "out": deg["out_degree"]},
            })

        edges_list = []
        for source, target in self.edges():
            edges_list.append({"source": source, "target": target})

        total_edges = len(edges_list)
        total_nodes = len(nodes_list)

        return {
            "nodes": nodes_list,
            "edges": edges_list,
            "stats": {
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "avg_degree": round(total_edges / total_nodes, 2) if total_nodes else 0,
            },
        }
