"""
图谱洞察引擎 — 发现惊奇连接 + 知识空白

基于 Phase 4 Step 1 (4-Signal) 和 Step 2 (Louvain) 的结果，
自动检测两种图谱洞察：

  1. 惊奇连接 — 跨社区边、跨类型边、中心↔边缘耦合
  2. 知识空白 — 孤立节点、稀疏社区、桥节点

全部确定性算法，零 LLM 成本。
"""
from collections import defaultdict

from src.core.graph import WikiGraph
from src.core.logging_config import get_logger

logger = get_logger("insights")

# 惊奇模式权重
WEIGHT_CROSS_COMMUNITY = 0.5
WEIGHT_CROSS_TYPE = 0.3
WEIGHT_HUB_SPOKE = 0.2

# 桥节点阈值：连接到多少个不同社区算"桥"
BRIDGE_COMMUNITY_THRESHOLD = 3


class InsightEngine:
    """图谱洞察引擎

    检测两种洞察：
    - 惊奇连接 (surprising connections)：图结构中的意外强关联
    - 知识空白 (knowledge gaps)：孤立、稀疏、脆弱节点
    """

    def __init__(self, graph: WikiGraph) -> None:
        """
        Args:
            graph: WikiGraph 实例（需已构建）
        """
        self.graph = graph

    # ------------------------------------------------------------------
    # 惊奇连接检测
    # ------------------------------------------------------------------

    def find_surprising_connections(
        self,
        community_result: dict,
        repo=None,
    ) -> list[dict]:
        """
        发现图谱中的"惊奇连接"

        三种惊奇模式：
          1. 跨社区边 (×0.5)：图算法认为它们属于不同社区，但有直接链接
          2. 跨类型边 (×0.3)：entity ↔ concept 异类关联
          3. 中心↔边缘耦合 (×0.2)：高度节点连接到低度节点

        Args:
            community_result: CommunityDetector.detect() 的返回结果
            repo: WikiRepository 实例（可选，提供后可检测跨类型边）

        Returns:
            按 surprise_score 降序排列的连接列表：
            [
                {
                    "source": "entities/python.md",
                    "target": "concepts/design_patterns.md",
                    "reason": "跨社区连接：社区0 ↔ 社区2",
                    "surprise_score": 0.85,
                    "connection_type": "cross_community",
                },
                ...
            ]
        """
        if not community_result:
            return []

        # 构建社区成员 → ID 映射
        node_to_community: dict[str, int] = {}
        for cid_str, cdata in community_result.get("communities", {}).items():
            cid = int(cid_str)
            for member in cdata.get("members", []):
                node_to_community[member] = cid

        # 构建节点类型映射
        node_types: dict[str, str] = {}
        if repo:
            for node in self.graph.nodes():
                meta = repo.get_page(node)
                if meta:
                    node_types[node] = meta.get("page_type", "")

        # 收集惊奇连接
        connections: list[dict] = []
        seen_pairs: set[tuple[str, str]] = set()

        for source, target in self.graph.edges():
            # 去重（无向边只处理一次）
            pair = (source, target) if source < target else (target, source)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            score = 0.0
            reasons: list[str] = []

            # 1. 跨社区边
            src_comm = node_to_community.get(source)
            tgt_comm = node_to_community.get(target)
            if src_comm is not None and tgt_comm is not None and src_comm != tgt_comm:
                score += WEIGHT_CROSS_COMMUNITY
                reasons.append(f"跨社区连接：社区{src_comm} ↔ 社区{tgt_comm}")

            # 2. 跨类型边
            src_type = node_types.get(source, "")
            tgt_type = node_types.get(target, "")
            if src_type and tgt_type and src_type != tgt_type:
                score += WEIGHT_CROSS_TYPE
                reasons.append(f"跨类型连接：{src_type} ↔ {tgt_type}")
                connection_type = "cross_type"
            elif src_comm != tgt_comm:
                connection_type = "cross_community"
            else:
                connection_type = "unexpected"

            # 3. 中心↔边缘耦合
            src_deg = self._total_degree(source)
            tgt_deg = self._total_degree(target)
            if src_deg >= 3 and tgt_deg <= 1:
                score += WEIGHT_HUB_SPOKE
                reasons.append(f"中心↔边缘耦合：度{src_deg} ↔ 度{tgt_deg}")
                connection_type = "hub_spoke" if not connection_type or connection_type == "unexpected" else connection_type
            elif tgt_deg >= 3 and src_deg <= 1:
                score += WEIGHT_HUB_SPOKE
                reasons.append(f"中心↔边缘耦合：度{src_deg} ↔ 度{tgt_deg}")
                connection_type = "hub_spoke" if not connection_type or connection_type == "unexpected" else connection_type

            if score > 0:
                connections.append({
                    "source": source,
                    "target": target,
                    "reason": "；".join(reasons),
                    "surprise_score": round(score, 2),
                    "connection_type": connection_type,
                })

        connections.sort(key=lambda c: c["surprise_score"], reverse=True)
        logger.info("惊奇连接检测完成 | total=%d", len(connections))
        return connections

    # ------------------------------------------------------------------
    # 知识空白检测
    # ------------------------------------------------------------------

    def find_knowledge_gaps(
        self,
        community_result: dict,
    ) -> list[dict]:
        """
        发现知识空白

        三种空白模式：
          1. 孤立节点 (degree ≤ 1)：只有一个连接的页面
          2. 稀疏社区 (cohesion < 0.15)：社区内部连接太少
          3. 桥节点：连接 3 个以上社区的关键页面

        Args:
            community_result: CommunityDetector.detect() 的返回结果

        Returns:
            [
                {
                    "type": "isolated",
                    "node": "concepts/forgotten.md",
                    "description": "此页面链接数为 1，可能处于知识孤岛",
                    "suggestion": "考虑与其他页面建立更多引用链接",
                },
                ...
            ]
        """
        gaps: list[dict] = []

        if not community_result:
            return gaps

        # 1. 孤立节点
        isolated_count = 0
        for node in self.graph.nodes():
            deg = self.graph.degree(node)
            total_deg = deg["in_degree"] + deg["out_degree"]
            if total_deg <= 1:
                isolated_count += 1
                gaps.append({
                    "type": "isolated",
                    "node": node,
                    "description": f"此页面链接数为 {total_deg}，可能处于知识孤岛",
                    "suggestion": "考虑与其他页面建立更多引用链接",
                })

        # 2. 稀疏社区
        sparse_count = 0
        for cid_str, cdata in community_result.get("communities", {}).items():
            cohesion = cdata.get("cohesion", 1.0)
            if cohesion < 0.15:
                sparse_count += 1
                # 对该社区的每个成员标记
                for member in cdata.get("members", []):
                    gaps.append({
                        "type": "sparse_community",
                        "node": member,
                        "description": (
                            f"所属社区（ID={cid_str}）内聚度仅 {cohesion}，"
                            "社区内部连接稀疏"
                        ),
                        "suggestion": "在此主题页面之间增加交叉引用",
                    })

        # 3. 桥节点：连接 3 个以上社区
        bridge_count = 0
        node_communities = self._build_node_community_map(community_result)
        for node in self.graph.nodes():
            connected_comms = node_communities.get(node, set())
            if len(connected_comms) >= BRIDGE_COMMUNITY_THRESHOLD:
                bridge_count += 1
                gaps.append({
                    "type": "bridge",
                    "node": node,
                    "description": (
                        f"此页面连接了 {len(connected_comms)} 个社区 "
                        f"（{', '.join(str(c) for c in sorted(connected_comms))}），"
                        "删除它可能导致图谱分裂"
                    ),
                    "suggestion": "考虑将关键内容拆分到多个页面",
                })

        logger.info(
            "知识空白检测完成 | isolated=%d sparse=%d bridge=%d",
            isolated_count, sparse_count, bridge_count,
        )
        return gaps

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _total_degree(self, node: str) -> int:
        """返回节点的总度（入度 + 出度）"""
        deg = self.graph.degree(node)
        return deg["in_degree"] + deg["out_degree"]

    def _build_node_community_map(self, community_result: dict) -> dict[str, set[int]]:
        """
        通过遍历图边构建 node → {邻居社区} 映射

        用于检测桥节点。
        """
        # 社区成员映射
        node_to_community: dict[str, int] = {}
        for cid_str, cdata in community_result.get("communities", {}).items():
            cid = int(cid_str)
            for member in cdata.get("members", []):
                node_to_community[member] = cid

        result: dict[str, set[int]] = defaultdict(set)
        for source, target in self.graph.edges():
            src_comm = node_to_community.get(source)
            tgt_comm = node_to_community.get(target)
            if src_comm is not None and tgt_comm is not None and src_comm != tgt_comm:
                result[source].add(tgt_comm)
                result[target].add(src_comm)

        return dict(result)

    # ------------------------------------------------------------------
    # 一站式入口
    # ------------------------------------------------------------------

    def analyze_all(
        self,
        community_result: dict,
        repo=None,
    ) -> dict:
        """
        一站式运行所有洞察分析

        Args:
            community_result: CommunityDetector.detect() 的返回结果
            repo: WikiRepository 实例（可选）

        Returns:
            {
                "surprising_connections": [...],
                "knowledge_gaps": [...],
                "summary": {
                    "total_surprising": 3,
                    "total_gaps": 5,
                    "gap_types": {"isolated": 2, "sparse_community": 2, "bridge": 1},
                },
            }
        """
        connections = self.find_surprising_connections(community_result, repo=repo)
        gaps = self.find_knowledge_gaps(community_result)

        # 统计缺口类型
        gap_types: dict[str, int] = {}
        for g in gaps:
            gap_types[g["type"]] = gap_types.get(g["type"], 0) + 1

        summary = {
            "total_surprising": len(connections),
            "total_gaps": len(gaps),
            "gap_types": gap_types,
        }

        return {
            "surprising_connections": connections,
            "knowledge_gaps": gaps,
            "summary": summary,
        }
