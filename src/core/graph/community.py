"""
Louvain 社区检测 — 基于 4-signal 加权边的自动知识聚类

利用 networkx + python-louvain 实现。
从 graph_relevance 表读取加权边构建无向图，运行 Louvain 算法
发现自动知识聚类（社区）。

全部确定性算法，零 LLM 成本（社区命名可选调用 LLM）。
"""

from src.core.graph.graph import WikiGraph
from src.core.logging_config import get_logger

logger = get_logger("community")

COHESION_THRESHOLD = 0.15  # 低内聚社区的阈值


class CommunityDetector:
    """Louvain 社区检测 — 自动发现 Wiki 知识聚类"""

    def __init__(self, graph: WikiGraph) -> None:
        """
        Args:
            graph: WikiGraph 实例（需已构建 + compute_relevance 已调用）
        """
        self.graph = graph
        self._partition: dict[str, int] = {}  # node → community_id
        self._communities: dict[int, dict] = {}
        self._modularity: float = 0.0

    def detect(self, repo=None) -> dict:
        """
        运行 Louvain 算法，检测社区结构

        需要一个已调用 compute_relevance() 的 WikiGraph，以便从
        graph_relevance 表中读取加权边。

        Args:
            repo: WikiRepository 实例，用于读取 graph_relevance 加权边数据

        Returns:
            {
                "communities": {
                    "0": {
                        "members": ["entities/python.md", ...],
                        "cohesion": 0.85,
                        "size": 12,
                    },
                    ...
                },
                "orphan_communities": ["3"],   # cohesion < 0.15 的社区 id
                "modularity": 0.72,
                "total_nodes": 20,
            }
        """
        # 从 graph_relevance 表读取加权边
        edges = self._load_weighted_edges(repo)

        # 如果边太少，每个节点单独成社区
        if len(edges) < 1:
            return self._fallback_singletons()

        # 构建 networkx 无向加权图
        nx_graph = self._build_nx_graph(edges)

        # 运行 Louvain
        self._partition, self._modularity = self._run_louvain(nx_graph)

        # 按社区分组
        self._communities = self._group_by_community(self._partition, nx_graph)

        # 组装返回结果
        result = self._build_result()

        logger.info(
            "社区检测完成 | communities=%d modularity=%.3f",
            len(self._communities), self._modularity,
        )
        return result

    # ------------------------------------------------------------------
    # 内部 — 数据加载
    # ------------------------------------------------------------------

    def _load_weighted_edges(self, repo) -> list[dict]:
        """
        从 graph_relevance 表加载加权边

        如果 repo 为 None 或表为空，从 WikiGraph 的基本 edges() 构建。
        """
        rows = []
        if repo:
            try:
                rows = repo.get_all_relevance()
            except Exception as exc:
                logger.warning("读取 graph_relevance 失败，降级到基本边 | %s", exc)

        if rows:
            return rows

        # 降级：从 WikiGraph.edges() 构建，权重 = 1
        nodes = self.graph.nodes()
        node_set = set(nodes)
        for source, target in self.graph.edges():
            if source in node_set and target in node_set:
                # 确保按字母顺序排序，匹配 relevance 表格式
                a, b = (source, target) if source < target else (target, source)
                rows.append({
                    "source_path": a,
                    "target_path": b,
                    "total_score": 1.0,
                })
        # 去重
        seen: set[tuple[str, str]] = set()
        deduped = []
        for r in rows:
            key = (r["source_path"], r["target_path"])
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        return deduped

    # ------------------------------------------------------------------
    # 内部 — networkx 构建
    # ------------------------------------------------------------------

    @staticmethod
    def _build_nx_graph(edges: list[dict]):
        """构建 networkx 无向加权图"""
        import networkx as nx

        G = nx.Graph()
        for e in edges:
            w = e.get("total_score", 1.0)
            if w > 0:
                G.add_edge(e["source_path"], e["target_path"], weight=w)
        return G

    # ------------------------------------------------------------------
    # 内部 — Louvain
    # ------------------------------------------------------------------

    @staticmethod
    def _run_louvain(G):
        """运行 Louvain 社区发现"""
        import community as community_louvain

        partition = community_louvain.best_partition(G, weight="weight")
        modularity = community_louvain.modularity(partition, G, weight="weight")
        return partition, modularity

    # ------------------------------------------------------------------
    # 内部 — 社区分组与内聚度
    # ------------------------------------------------------------------

    @staticmethod
    def _group_by_community(partition: dict, G) -> dict[int, dict]:
        """按 community_id 分组，计算每个社区的内聚度"""
        # 按社区分组
        comm_members: dict[int, list[str]] = {}
        for node, cid in partition.items():
            comm_members.setdefault(cid, []).append(node)

        # 计算每个社区的内聚度
        communities: dict[int, dict] = {}
        for cid, members in comm_members.items():
            member_set = set(members)
            internal_weight = 0.0
            total_weight = 0.0

            for u, v, data in G.edges(data=True):
                w = data.get("weight", 1.0)
                u_in = u in member_set
                v_in = v in member_set
                if u_in or v_in:
                    total_weight += w
                    if u_in and v_in:
                        internal_weight += w

            cohesion = round(internal_weight / total_weight, 4) if total_weight > 0 else 0.0

            communities[cid] = {
                "members": sorted(members),
                "cohesion": cohesion,
                "size": len(members),
            }

        return communities

    # ------------------------------------------------------------------
    # 内部 — 结果组装
    # ------------------------------------------------------------------

    def _build_result(self) -> dict:
        """组装最终结果"""
        # 字符串化 community_id 以便 JSON 序列化
        communities_out: dict[str, dict] = {
            str(cid): data for cid, data in self._communities.items()
        }

        # 标记低内聚社区
        orphan_ids: list[str] = [
            str(cid) for cid, data in self._communities.items()
            if data["cohesion"] < COHESION_THRESHOLD
        ]

        return {
            "communities": communities_out,
            "orphan_communities": orphan_ids,
            "modularity": round(self._modularity, 4),
            "total_nodes": sum(c["size"] for c in self._communities.values()),
        }

    def _fallback_singletons(self) -> dict:
        """降级：每个节点单独成社区"""
        nodes = self.graph.nodes()
        communities_out: dict[str, dict] = {}
        for i, node in enumerate(nodes):
            cid = str(i)
            communities_out[cid] = {
                "members": [node],
                "cohesion": 1.0,
                "size": 1,
            }

        # 所有孤页视为 orphan
        orphan_ids = list(communities_out.keys()) if len(nodes) > 1 else []

        return {
            "communities": communities_out,
            "orphan_communities": orphan_ids if len(nodes) > 1 else [],
            "modularity": 0.0,
            "total_nodes": len(nodes),
        }

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def partition(self) -> dict[str, int]:
        """返回 node → community_id 映射"""
        return self._partition

    @property
    def communities(self) -> dict[int, dict]:
        """返回社区详情"""
        return self._communities

    @property
    def modularity(self) -> float:
        """返回整体模块度"""
        return self._modularity

    def get_community_id(self, node: str) -> int | None:
        """返回节点所属的社区 ID"""
        return self._partition.get(node, None)
