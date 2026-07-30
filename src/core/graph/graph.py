"""
Wiki 页面关系图 — 纯确定性算法解析 [[wikilinks]]

通过正则解析 Markdown 中的双向链接，构建有向图。
零 LLM 调用，1000 页以内 < 100ms。

Phase 4 增强：4-Signal 加权关联度模型。
"""
import hashlib
import json
import math
import os
import re
import sqlite3
from collections import defaultdict

from src.core.logging_config import get_logger
from src.utils.path_resolver import get_db_path

logger = get_logger("graph")

# ---------------------------------------------------------------------------
# Wikilinks 正则模式
# ---------------------------------------------------------------------------
# 匹配 [[target]] 和 [[target|display_name]]
WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]+)?\]\]")

# 导航文件（不计入图节点）
NAV_FILES = {"index.md", "overview.md", "log.md"}

# ---------------------------------------------------------------------------
# 4-Signal 模型权重
# ---------------------------------------------------------------------------

SIGNAL_WEIGHTS = {
    "direct_link": 3.0,     # [[wikilinks]] 直接相连
    "source_overlap": 4.0,  # 共享同一原始 source 文件（最强信号）
    "adamic_adar": 1.5,     # 共享共同邻居，按 log(度) 反比加权
    "type_affinity": 1.0,   # 同类型页面加分
}

# Frontmatter sources 提取正则
SOURCES_PATTERN = re.compile(
    r"^sources:\s*$.*?(?=^[a-z]|^\s*$)",
    re.MULTILINE | re.DOTALL,
)


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


def parse_frontmatter_sources(content: str) -> list[str]:
    """
    从页面 YAML frontmatter 中提取 sources 字段

    解析 ---\n...\n--- 块中的 sources: 列表。
    支持 JSON 列表格式（sources: [a, b]）和 YAML 列表格式（sources:\n  - a\n  - b）。

    Args:
        content: 页面完整 Markdown 内容

    Returns:
        sources 值列表（如 ["raw/sources/file.md"]），无则返回 []
    """
    # 提取 frontmatter 块
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not fm_match:
        return []
    frontmatter = fm_match.group(1)

    sources: list[str] = []
    for line in frontmatter.split("\n"):
        stripped = line.strip()
        # JSON 列表格式：sources: [a, b]
        if stripped.startswith("sources:") and "[" in stripped:
            # 提取括号内的内容
            arr_match = re.search(r"\[(.*?)\]", stripped)
            if arr_match:
                items = [x.strip().strip("\"'") for x in arr_match.group(1).split(",")]
                sources.extend(items)
        # YAML 列表格式：  - value
        elif stripped.startswith("- "):
            val = stripped[2:].strip().strip("\"'")
            if val:
                sources.append(val)

    return sources


def _read_file_safe(file_path: str) -> str | None:
    """安全读取文件，失败返回 None"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as exc:
        logger.debug("无法读取文件 | path=%s error=%s", file_path, exc)
        return None


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
        self._dirty = False  # 懒重建标志

    # ------------------------------------------------------------------
    # 缓存持久化（graph_cache 表）
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_signature(wiki_dir: str = "wiki") -> str:
        """计算 wiki/ 目录的文件签名，用于缓存失效检测

        签名 = SHA256 所有 .md 文件的 (相对路径 + mtime)。
        文件没变 -> 签名不变 -> 缓存有效。
        """
        h = hashlib.sha256()
        if not os.path.isdir(wiki_dir):
            return h.hexdigest()
        for root, _dirs, files in os.walk(wiki_dir):
            for f in sorted(files):
                if not f.endswith(".md"):
                    continue
                rel = os.path.relpath(os.path.join(root, f), wiki_dir)
                path = os.path.join(root, f)
                try:
                    mtime = os.path.getmtime(path)
                    h.update(f"{rel}:{mtime}\n".encode())
                except OSError:
                    pass
        return h.hexdigest()

    def save_cache(self, db_path: str | None = None) -> None:
        """将当前图谱写入 graph_cache 表

        Args:
            db_path: SQLite 数据库路径，None 时使用 %APPDATA%/LLM-Wiki/wiki.db
        """
        from src.db.schema import CREATE_TABLES
        resolved = db_path if db_path is not None else get_db_path("wiki.db")
        conn = sqlite3.connect(resolved)
        conn.executescript(CREATE_TABLES)

        sig = self._compute_signature(self.wiki_dir)
        graph_data = {
            "adj": {k: v for k, v in self._adj.items()},
            "backlinks": {k: v for k, v in self._backlinks.items()},
            "in_degree": dict(self._in_degree),
            "out_degree": dict(self._out_degree),
        }

        conn.execute(
            "INSERT OR REPLACE INTO graph_cache "
            "(id, signature, nodes_json, edges_json, built_at) "
            "VALUES (1, ?, ?, ?, datetime('now'))",
            (sig, json.dumps(list(self._adj.keys())), json.dumps(graph_data)),
        )
        conn.commit()
        conn.close()
        logger.info("WikiGraph 缓存已写入 | nodes=%d", len(self._adj))

    def load_cache(self, db_path: str | None = None) -> bool:
        """尝试从 graph_cache 加载图谱

        Args:
            db_path: SQLite 数据库路径，None 时使用 %APPDATA%/LLM-Wiki/wiki.db

        Returns:
            True - 加载成功（缓存有效），False - 无缓存或签名不匹配
        """
        try:
            resolved = db_path if db_path is not None else get_db_path("wiki.db")
            conn = sqlite3.connect(resolved)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM graph_cache WHERE id = 1"
            ).fetchone()
            conn.close()

            if not row:
                return False

            current_sig = self._compute_signature(self.wiki_dir)
            if row["signature"] != current_sig:
                logger.info("WikiGraph 缓存签名不匹配，需要重建")
                return False

            graph_data = json.loads(row["edges_json"])
            self._adj = defaultdict(list, graph_data.get("adj", {}))
            self._backlinks = defaultdict(list, graph_data.get("backlinks", {}))
            self._in_degree = defaultdict(int, graph_data.get("in_degree", {}))
            self._out_degree = defaultdict(int, graph_data.get("out_degree", {}))
            self._built = True
            self._dirty = False

            logger.info("WikiGraph 从缓存加载 | nodes=%d sig=%s..",
                        len(self._adj), current_sig[:12])
            return True

        except Exception as exc:
            logger.warning("WikiGraph 缓存加载失败，将重建 | %s", exc)
            return False

    @classmethod
    def compute_and_cache(cls, db_path: str | None = None) -> "WikiGraph":
        """构建图谱 + 计算关联度 + 写入缓存（一次写入，后续启动从缓存加载）

        第一启动：全量扫描 + N² 计算 + 写入 DB
        后续启动：签名匹配 → 直接加载缓存（零扫描，零计算）
        文件变化：ingest 后 invalidate() → 下回读取触发增量查/重建

        Args:
            db_path: SQLite 数据库路径，None 时使用 %APPDATA%/LLM-Wiki/wiki.db
        """
        resolved = db_path if db_path is not None else get_db_path("wiki.db")
        graph = cls()

        # 优先从缓存加载——无文件变化时零操作
        if graph.load_cache(resolved):
            logger.info("WikiGraph 缓存命中，跳过预热")
            return graph

        # 缓存缺失或签名不匹配 → 全量构建
        from src.db.repository import WikiRepository

        graph.build()
        repo = WikiRepository()
        graph.compute_relevance(repo)
        graph.save_cache(resolved)
        logger.info("WikiGraph 预热完成 | nodes=%d", len(graph.nodes()))
        return graph

    # ------------------------------------------------------------------
    # 构建
    # ------------------------------------------------------------------

    def invalidate(self) -> None:
        """
        标记图为"脏"状态

        调用后，下次 nodes()/edges()/to_dict()/neighbors() 等读取方法
        会自动触发 build() + compute_relevance()（如果 repo 已传入）。
        高频路径（如 ingest）只需 O(1) 标记，无需全量扫描。
        """
        self._dirty = True
        self._built = False

    def _ensure_built(self, repo=None) -> None:
        """
        确保图已构建：优先从缓存加载，缓存失效则全量重建

        在 to_dict()、neighbors() 等读取方法入口调用。
        """
        if self._dirty or not self._built:
            # 第一优先：尝试从 DB 缓存加载（避免全量扫描文件）
            if not self._dirty and not self._built and self.load_cache():
                # relevance 已在 warmup/rebuild 时写入 graph_relevance 表，不需重复计算
                return

            self._adj.clear()
            self._backlinks.clear()
            self._in_degree.clear()
            self._out_degree.clear()
            self.build()
            if repo:
                self.compute_relevance(repo)
            self._dirty = False

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
        self._ensure_built()
        return sorted(self._adj.keys())

    def edges(self) -> list[tuple[str, str]]:
        """返回所有有向边 (source → target)"""
        self._ensure_built()
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
        self._ensure_built()

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
        self._ensure_built()
        return self._backlinks.get(path, [])

    def degree(self, path: str) -> dict:
        """
        返回节点的出入度

        Args:
            path: 页面路径

        Returns:
            {"in_degree": N, "out_degree": N}，节点不存在时返回 0/0
        """
        self._ensure_built()
        return {
            "in_degree": self._in_degree.get(path, 0),
            "out_degree": self._out_degree.get(path, 0),
        }

    # ------------------------------------------------------------------
    # 4-Signal 关联度
    # ------------------------------------------------------------------

    def compute_relevance(self, repo, target_nodes: list[str] | None = None) -> None:
        """
        计算 4-signal 关联度，写入 SQLite

        Args:
            repo: WikiRepository 实例
            target_nodes: 增量计算的节点列表。不传则全量计算。
        """
        self._ensure_built()
        engine = RelevanceSignal(graph=self, repo=repo, wiki_dir=self.wiki_dir)
        results = engine.compute_all(target_nodes=target_nodes)
        if results:
            repo.save_relevance(results)

    def related_pages(self, path: str, repo, limit: int = 20) -> list[dict]:
        """
        返回与指定页面最相关的 N 个页面（按 total_score 降序）

        Args:
            path: 页面路径
            repo: WikiRepository 实例
            limit: 最多返回条数

        Returns:
            按分数降序的关联页面列表
        """
        self._ensure_built()
        return repo.get_related_pages(path, limit=limit)

    # ------------------------------------------------------------------
    # 社区检测
    # ------------------------------------------------------------------

    def communities(self, repo=None) -> dict:
        """
        运行 Louvain 社区检测并返回结果

        Args:
            repo: WikiRepository 实例（提供时使用 graph_relevance 加权边）

        Returns:
            {
                "communities": {...},
                "orphan_communities": [...],
                "modularity": 0.72,
                "total_nodes": 20,
            }
        """
        from src.core.graph.community import CommunityDetector

        detector = CommunityDetector(self)
        return detector.detect(repo=repo)

    # ------------------------------------------------------------------
    # 图谱洞察
    # ------------------------------------------------------------------

    def insights(self, community_result: dict, repo=None) -> dict:
        """
        运行图谱洞察引擎，返回惊奇连接 + 知识空白

        Args:
            community_result: communities() 返回的社区检测结果
            repo: WikiRepository 实例（可选，用于跨类型边检测）

        Returns:
            {
                "surprising_connections": [...],
                "knowledge_gaps": [...],
                "summary": {...},
            }
        """
        from src.core.graph.insights import InsightEngine

        engine = InsightEngine(self)
        return engine.analyze_all(community_result, repo=repo)

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self, repo=None) -> dict:
        """
        返回图数据的 JSON 友好结构，供 API 使用

        Args:
            repo: WikiRepository 实例（可选）。提供时返回增强数据
                  （page_type、边权重、信号分项）

        Returns:
            {
                "nodes": [
                    {"id": "...", "degree": {"in": 2, "out": 3},
                     "page_type": "entity"},
                    ...
                ],
                "edges": [
                    {"source": "...", "target": "...",
                     "weight": 7.2, "signals": {"direct_link": 3.0, ...}},
                    ...
                ],
                "stats": {"total_nodes": 10, "total_edges": 15, "avg_degree": 3.0},
            }
        """
        self._ensure_built(repo=repo)

        # 运行社区检测，构建 community_id 映射
        community_map: dict[str, str] = {}  # node → community_id
        if repo:
            try:
                comm_result = self.communities(repo=repo)
                for cid_str, cdata in comm_result.get("communities", {}).items():
                    for member in cdata.get("members", []):
                        community_map[member] = cid_str
            except Exception as exc:
                logger.debug("社区检测失败，跳过 community_id | %s", exc)

        # 构建节点列表
        page_types: dict[str, str] = {}
        if repo:
            for node in self.nodes():
                meta = repo.get_page(node)
                if meta:
                    page_types[node] = meta.get("page_type", "")

        nodes_list = []
        for node in self.nodes():
            deg = self.degree(node)
            entry: dict = {
                "id": node,
                "degree": {"in": deg["in_degree"], "out": deg["out_degree"]},
            }
            if page_types.get(node):
                entry["page_type"] = page_types[node]
            cid = community_map.get(node)
            if cid is not None:
                entry["community_id"] = int(cid)
            nodes_list.append(entry)

        # 构建边列表
        edges_list = []
        if repo:
            # 从 graph_relevance 表获取加权边
            for source in self.nodes():
                related = repo.get_related_pages(source, limit=1000)
                for r in related:
                    edges_list.append({
                        "source": source,
                        "target": r["target_path"],
                        "weight": r["total_score"],
                        "signals": {
                            "direct_link": r["direct_link"],
                            "source_overlap": r["source_overlap"],
                            "adamic_adar": r["adamic_adar"],
                            "type_affinity": r["type_affinity"],
                        },
                    })
        else:
            # 基本模式：只返回有向边
            for source, target in self.edges():
                edges_list.append({"source": source, "target": target})

        total_edges = len(edges_list)
        total_nodes = len(nodes_list)

        result: dict = {
            "nodes": nodes_list,
            "edges": edges_list,
            "stats": {
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "avg_degree": round(total_edges / total_nodes, 2) if total_nodes else 0,
            },
        }

        # 如果有社区检测结果，一并返回
        if repo and community_map:
            try:
                comm_result = self.communities(repo=repo)
                result["communities"] = comm_result.get("communities", {})
                result["modularity"] = comm_result.get("modularity", 0.0)

                # 图谱洞察
                insight_result = self.insights(comm_result, repo=repo)
                result["insights"] = insight_result.get("summary", {})
                result["surprising_connections"] = insight_result.get("surprising_connections", [])
                result["knowledge_gaps"] = insight_result.get("knowledge_gaps", [])
            except Exception as exc:
                logger.debug("to_dict 社区/洞察检测失败 | %s", exc)

        return result


# ============================================================================
# Phase 4 — 4-Signal 关联度模型
# ============================================================================


class RelevanceSignal:
    """4-Signal 加权关联度计算引擎

    计算两个 wiki 页面之间的关联度分数，由 4 个信号加权求和：
      1. direct_link (×3.0) — [[wikilinks]] 直接相连
      2. source_overlap (×4.0) — 共享同一原始文件（最强信号）
      3. adamic_adar (×1.5) — 共享共同邻居，按度反比加权
      4. type_affinity (×1.0) — 同类型页面加分

    全部确定性算法，零 LLM 成本。
    """

    def __init__(self, graph: WikiGraph, repo, wiki_dir: str = "wiki") -> None:
        """
        Args:
            graph: WikiGraph 实例
            repo: WikiRepository 实例
            wiki_dir: wiki 文件目录路径
        """
        self.graph = graph
        self.repo = repo
        self.wiki_dir = wiki_dir

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def compute_all(self, target_nodes: list[str] | None = None) -> list[dict]:
        """
        计算 4 信号加权关联度

        Args:
            target_nodes: 指定只计算这些节点与所有节点的关联度（增量模式）。
                          不传则计算所有 N² 对（全量模式）。

        Returns:
            list[dict]: [
                {"source_path": "...", "target_path": "...",
                 "total_score": 8.5, "direct_link": 3.0,
                 "source_overlap": 4.0, "adamic_adar": 0, "type_affinity": 1.5},
                ...
            ]
        """
        all_nodes = self.graph.nodes()
        if len(all_nodes) < 2:
            return []

        # 决定计算哪些节点对
        if target_nodes:
            # 增量模式：只计算 target_nodes 与所有节点
            nodes_a = [n for n in target_nodes if n in all_nodes]
            nodes_b = all_nodes
        else:
            # 全量模式：计算所有 N²/2 对
            nodes_a = all_nodes
            nodes_b = None  # 表示使用 i+1 遍历

        if not nodes_a:
            return []

        # 预计算各信号所需的数据
        sources_map = self._build_sources_map()
        type_map = self._build_type_map()
        node_set = set(all_nodes)

        # adjacency set for O(1) lookup
        adj_sets: dict[str, set[str]] = {}
        for n in all_nodes:
            adj_sets[n] = set()
        for source, target in self.graph.edges():
            if source in adj_sets and target in node_set:
                adj_sets[source].add(target)
                adj_sets.setdefault(target, set()).add(source)

        degree_cache: dict[str, int] = {}
        for n in all_nodes:
            deg = self.graph.degree(n)
            degree_cache[n] = deg["in_degree"] + deg["out_degree"]

        results: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()

        def compute_pair(a: str, b: str) -> None:
            if a == b:
                return
            key = (a, b) if a < b else (b, a)
            if key in seen_pairs:
                return
            seen_pairs.add(key)

            dl = self._direct_link(a, b, adj_sets)
            so = self._source_overlap(a, b, sources_map)
            aa = self._adamic_adar(a, b, adj_sets, degree_cache)
            ta = self._type_affinity(a, b, type_map)

            total = (
                dl * SIGNAL_WEIGHTS["direct_link"]
                + so * SIGNAL_WEIGHTS["source_overlap"]
                + aa * SIGNAL_WEIGHTS["adamic_adar"]
                + ta * SIGNAL_WEIGHTS["type_affinity"]
            )

            if total <= 0:
                return

            results.append({
                "source_path": key[0],
                "target_path": key[1],
                "total_score": round(total, 2),
                "direct_link": round(dl, 2),
                "source_overlap": round(so, 2),
                "adamic_adar": round(aa, 4),
                "type_affinity": round(ta, 2),
            })

        if target_nodes:
            # 增量：每个 target × 所有节点
            for a in nodes_a:
                for b in nodes_b:
                    compute_pair(a, b)
        else:
            # 全量：N²/2
            for i, a in enumerate(nodes_a):
                for b in nodes_a[i + 1:]:
                    compute_pair(a, b)

        results.sort(key=lambda r: r["total_score"], reverse=True)
        mode = "增量" if target_nodes else "全量"
        logger.info(
            "RelevanceSignal 计算完成 | mode=%s nodes=%d pairs=%d",
            mode, len(all_nodes), len(results),
        )
        return results

    # ------------------------------------------------------------------
    # 信号：direct_link
    # ------------------------------------------------------------------

    @staticmethod
    def _direct_link(path_a: str, path_b: str, adj_sets: dict[str, set[str]]) -> float:
        if path_b in adj_sets.get(path_a, set()):
            return 1.0
        if path_a in adj_sets.get(path_b, set()):
            return 1.0
        return 0.0

    # ------------------------------------------------------------------
    # 信号：source_overlap
    # ------------------------------------------------------------------

    def _build_sources_map(self) -> dict[str, list[str]]:
        sources_map: dict[str, list[str]] = {}
        for node in self.graph.nodes():
            full_path = os.path.join(self.wiki_dir, node)
            content = _read_file_safe(full_path)
            if content:
                sources = parse_frontmatter_sources(content)
                if sources:
                    sources_map[node] = sources
        return sources_map

    @staticmethod
    def _source_overlap(path_a, path_b, sources_map):
        sa = sources_map.get(path_a, [])
        sb = sources_map.get(path_b, [])
        if not sa or not sb:
            return 0.0
        common = set(sa) & set(sb)
        return float(len(common))

    # ------------------------------------------------------------------
    # 信号：adamic_adar
    # ------------------------------------------------------------------

    @staticmethod
    def _adamic_adar(path_a, path_b, adj_sets, degree_cache):
        neighbors_a = adj_sets.get(path_a, set())
        neighbors_b = adj_sets.get(path_b, set())
        common = neighbors_a & neighbors_b
        if not common:
            return 0.0

        score = 0.0
        for n in common:
            deg = degree_cache.get(n, 1)
            if deg > 1:
                score += 1.0 / math.log(deg)
            else:
                score += 1.0
        return score

    # ------------------------------------------------------------------
    # 信号：type_affinity
    # ------------------------------------------------------------------

    def _build_type_map(self) -> dict[str, str]:
        type_map: dict[str, str] = {}
        for node in self.graph.nodes():
            meta = self.repo.get_page(node)
            if meta:
                type_map[node] = meta.get("page_type", "")
        return type_map

    @staticmethod
    def _type_affinity(path_a, path_b, type_map):
        ta = type_map.get(path_a, "")
        tb = type_map.get(path_b, "")
        if ta and tb and ta == tb:
            return 1.0
        return 0.0


# ============================================================================
# 后台重建（供 app_state / TaskQueue 调用）
# ============================================================================


def rebuild_graph(payload: dict | None = None) -> None:
    """重建图谱 + 关联度 + 写缓存

    被 TaskQueue 注册为 "rebuild_graph" 事件的处理器。
    也会被 _warmup_graph() 调用做启动预热。
    结果持久化到 graph_cache + graph_relevance 表。
    """
    logger.info("后台任务开始重建图谱...")
    WikiGraph.compute_and_cache()
    logger.info("后台任务图谱重建完成")
