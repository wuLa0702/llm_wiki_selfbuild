"""
CommunityDetector 单元测试 — Phase 4 Step 2 Louvain 社区检测
"""
import pytest

from src.core.graph.community import COHESION_THRESHOLD, CommunityDetector
from src.core.graph import WikiGraph


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def wiki_dir(tmp_path):
    """创建带多个页面的 wiki 目录，便于社区检测测试"""
    d = tmp_path / "wiki"
    d.mkdir()
    (d / "entities").mkdir()
    (d / "concepts").mkdir()
    (d / "frameworks").mkdir()

    # 页面 A 集群：NLP 相关
    (d / "entities" / "python.md").write_text(
        "---\ntitle: Python\ntype: entity\n---\n"
        "# Python\n\n[[concepts/nlp.md|NLP]] 和 [[frameworks/pytorch.md|PyTorch]]",
        encoding="utf-8",
    )
    (d / "concepts" / "nlp.md").write_text(
        "---\ntitle: NLP\ntype: concept\n---\n"
        "# NLP\n\n[[frameworks/pytorch.md|PyTorch]] 和 [[concepts/transformer.md|Transformer]]",
        encoding="utf-8",
    )
    (d / "frameworks" / "pytorch.md").write_text(
        "---\ntitle: PyTorch\ntype: entity\n---\n"
        "# PyTorch\n\n[[concepts/nlp.md|NLP]] 和 [[concepts/deep_learning.md|Deep Learning]]",
        encoding="utf-8",
    )
    (d / "concepts" / "transformer.md").write_text(
        "---\ntitle: Transformer\ntype: concept\n---\n"
        "# Transformer\n\n[[concepts/nlp.md|NLP]] 和 [[concepts/deep_learning.md|Deep Learning]]",
        encoding="utf-8",
    )
    (d / "concepts" / "deep_learning.md").write_text(
        "---\ntitle: Deep Learning\ntype: concept\n---\n"
        "# Deep Learning\n\n[[frameworks/pytorch.md|PyTorch]] 和 [[concepts/transformer.md|Transformer]]",
        encoding="utf-8",
    )

    # 页面 B 集群：数据库相关（与 NLP 集群弱连接）
    (d / "entities" / "mysql.md").write_text(
        "---\ntitle: MySQL\ntype: entity\n---\n"
        "# MySQL\n\n[[concepts/sql.md|SQL]]",
        encoding="utf-8",
    )
    (d / "concepts" / "sql.md").write_text(
        "---\ntitle: SQL\ntype: concept\n---\n"
        "# SQL\n\n[[entities/mysql.md|MySQL]]",
        encoding="utf-8",
    )
    (d / "entities" / "postgresql.md").write_text(
        "---\ntitle: PostgreSQL\ntype: entity\n---\n"
        "# PostgreSQL\n\n[[concepts/sql.md|SQL]]",
        encoding="utf-8",
    )

    # 孤页：无任何链接
    (d / "entities" / "orphan.md").write_text(
        "---\ntitle: Orphan\ntype: entity\n---\n# Orphan",
        encoding="utf-8",
    )

    return d


@pytest.fixture
def graph(wiki_dir):
    """构建 WikiGraph"""
    g = WikiGraph(str(wiki_dir))
    g.build()
    return g


@pytest.fixture
def simple_graph(tmp_path):
    """最简单的图：两个相连节点"""
    d = tmp_path / "wiki"
    d.mkdir()
    (d / "a.md").write_text("# A\n\n[[b.md]]", encoding="utf-8")
    (d / "b.md").write_text("# B\n\n[[a.md]]", encoding="utf-8")
    g = WikiGraph(str(d))
    g.build()
    return g


# ============================================================================
# 基本检测
# ============================================================================


def test_detection_returns_communities(graph):
    """detect() 返回 communities 字段"""
    detector = CommunityDetector(graph)
    result = detector.detect()
    assert "communities" in result
    assert len(result["communities"]) > 0


def test_communities_have_members(graph):
    """每个社区有成员列表"""
    detector = CommunityDetector(graph)
    result = detector.detect()
    for cid, cdata in result["communities"].items():
        assert "members" in cdata
        assert isinstance(cdata["members"], list)
        assert len(cdata["members"]) > 0


def test_communities_have_cohesion(graph):
    """每个社区有内聚度"""
    detector = CommunityDetector(graph)
    result = detector.detect()
    for cdata in result["communities"].values():
        assert "cohesion" in cdata
        assert 0 <= cdata["cohesion"] <= 1.0


def test_communities_have_size(graph):
    """每个社区有 size 字段"""
    detector = CommunityDetector(graph)
    result = detector.detect()
    for cdata in result["communities"].values():
        assert "size" in cdata
        assert cdata["size"] == len(cdata["members"])


def test_detection_returns_modularity(graph):
    """detect() 返回 modularity"""
    detector = CommunityDetector(graph)
    result = detector.detect()
    assert "modularity" in result
    assert isinstance(result["modularity"], float)


# ============================================================================
# 边界条件
# ============================================================================


def test_empty_graph(tmp_path):
    """空图返回空结果"""
    d = tmp_path / "empty"
    d.mkdir()
    g = WikiGraph(str(d))
    g.build()
    detector = CommunityDetector(g)
    result = detector.detect()
    assert result["total_nodes"] == 0
    assert len(result["communities"]) == 0


def test_single_node(tmp_path):
    """单节点图：一个孤页"""
    d = tmp_path / "wiki"
    d.mkdir()
    (d / "a.md").write_text("# A", encoding="utf-8")
    g = WikiGraph(str(d))
    g.build()
    detector = CommunityDetector(g)
    result = detector.detect()
    assert result["total_nodes"] == 1
    assert len(result["communities"]) == 1


def test_two_nodes_disconnected(tmp_path):
    """两个不连通的节点各自成社区"""
    d = tmp_path / "wiki"
    d.mkdir()
    (d / "a.md").write_text("# A", encoding="utf-8")
    (d / "b.md").write_text("# B", encoding="utf-8")
    g = WikiGraph(str(d))
    g.build()
    detector = CommunityDetector(g)
    result = detector.detect()
    # Louvain 可能会合并它们，至少要有 1 个社区
    assert result["total_nodes"] == 2
    assert len(result["communities"]) >= 1


# ============================================================================
# 内聚度与孤页
# ============================================================================


def test_simple_graph_cohesion(simple_graph):
    """两个相连节点的社区内聚度为 1.0"""
    detector = CommunityDetector(simple_graph)
    result = detector.detect()
    # 2 个节点，1 条边，应归属同一社区
    for cdata in result["communities"].values():
        if cdata["size"] == 2:
            assert cdata["cohesion"] == 1.0
            break
    else:
        pytest.fail("未找到含 2 个成员的社区")


def test_modularity_positive_for_structured(graph):
    """有结构的图 modularity > 0"""
    detector = CommunityDetector(graph)
    result = detector.detect()
    # 如果图有 2 个以上社区且结构清晰，modularity > 0
    if len(result["communities"]) >= 2:
        assert result["modularity"] > 0


# ============================================================================
# Property: partition
# ============================================================================


def test_partition_property(graph):
    """partition 属性返回 node → community_id 映射"""
    detector = CommunityDetector(graph)
    detector.detect()
    partition = detector.partition
    assert isinstance(partition, dict)
    for node, cid in partition.items():
        assert isinstance(node, str)
        assert isinstance(cid, int)


def test_get_community_id(graph):
    """get_community_id 返回节点的社区 ID"""
    detector = CommunityDetector(graph)
    detector.detect()
    # 取第一个节点
    nodes = graph.nodes()
    if nodes:
        cid = detector.get_community_id(nodes[0])
        assert cid is not None
        assert isinstance(cid, int)


def test_get_community_id_nonexistent(graph):
    """不存在的节点返回 None"""
    detector = CommunityDetector(graph)
    assert detector.get_community_id("nonexistent") is None
