"""
WikiGraph 单元测试
"""
import os

import pytest

from src.core.graph import WikiGraph, parse_wikilinks


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def wiki_dir(tmp_path):
    d = tmp_path / "wiki"
    d.mkdir()

    # 创建实体页面
    (d / "entities").mkdir()
    (d / "entities" / "python.md").write_text(
        "---\ntitle: Python\ntype: entity\n---\n"
        "# Python\n\n[[concepts/ai.md|AI]] 和 [[entities/java.md|Java]]",
        encoding="utf-8",
    )
    (d / "entities" / "java.md").write_text(
        "---\ntitle: Java\ntype: entity\n---\n"
        "# Java\n\n[[concepts/ai.md]]",
        encoding="utf-8",
    )

    # 创建概念页面
    (d / "concepts").mkdir()
    (d / "concepts" / "ai.md").write_text(
        "---\ntitle: AI\ntype: concept\n---\n"
        "# AI\n\n[[entities/python.md]]",
        encoding="utf-8",
    )
    (d / "concepts" / "ml.md").write_text(
        "---\ntitle: ML\ntype: concept\n---\n"
        "# ML\n\n指向不存在的页面 [[entities/nonexistent.md]]",
        encoding="utf-8",
    )

    # 导航文件
    (d / "index.md").write_text("# Index\n\n[[entities/python.md]]", encoding="utf-8")
    return d


# ============================================================================
# parse_wikilinks
# ============================================================================


def test_parse_wikilinks_simple():
    """普通 [[target]] 被提取"""
    assert parse_wikilinks("Hello [[entities/python.md]] world") == ["entities/python.md"]


def test_parse_wikilinks_with_display():
    """[[target|display]] 提取 target"""
    assert parse_wikilinks("See [[concepts/ai.md|AI 详情]]") == ["concepts/ai.md"]


def test_parse_wikilinks_multiple():
    """多个 wikilinks 全部提取"""
    text = "A [[a.md]] and [[b.md]] and [[a.md]]"
    result = parse_wikilinks(text)
    assert result == ["a.md", "b.md"]  # 去重


def test_parse_wikilinks_none():
    """无 wikilinks 返回空列表"""
    assert parse_wikilinks("No links here") == []


def test_parse_wikilinks_with_anchor():
    """[[page#section]] 提取 page"""
    result = parse_wikilinks("See [[concepts/ai.md#attention|注意力]]")
    assert result == ["concepts/ai.md"]


# ============================================================================
# WikiGraph.build
# ============================================================================


def test_build_nodes(wiki_dir):
    """build() 后 nodes() 包含所有 wiki 页面"""
    g = WikiGraph(str(wiki_dir))
    g.build()
    nodes = g.nodes()
    assert "entities/python.md" in nodes
    assert "entities/java.md" in nodes
    assert "concepts/ai.md" in nodes
    assert "index.md" in nodes  # 导航文件也计入节点（不是孤页）


def test_build_edges(wiki_dir):
    """build() 后 edges() 包含所有有向边"""
    g = WikiGraph(str(wiki_dir))
    g.build()
    edges = g.edges()
    # python.md → ai.md
    assert ("entities/python.md", "concepts/ai.md") in edges
    # python.md → java.md
    assert ("entities/python.md", "entities/java.md") in edges
    # java.md → ai.md
    assert ("entities/java.md", "concepts/ai.md") in edges
    # ai.md → python.md
    assert ("concepts/ai.md", "entities/python.md") in edges


# ============================================================================
# neighbors / backlinks / degree
# ============================================================================


def test_neighbors_depth1(wiki_dir):
    """neighbors(path, depth=1) 返回直接关联页面（正+反向）"""
    g = WikiGraph(str(wiki_dir))
    g.build()
    # python.md 指向 ai.md 和 java.md；ai.md 指向 python.md
    n = g.neighbors("entities/python.md", depth=1)
    assert "concepts/ai.md" in n  # python → ai
    assert "entities/java.md" in n  # python → java
    # ai.md → python.md，但 python 已经 visited 了，所以不在结果里


def test_neighbors_depth2(wiki_dir):
    """neighbors(path, depth=2) 返回二跳关联"""
    g = WikiGraph(str(wiki_dir))
    g.build()
    # python → ai → python（visited, skipped）
    # python → java → ai（already found），只有新节点
    n = g.neighbors("entities/python.md", depth=2)
    assert "concepts/ml.md" not in n  # ml 没有与 python 直接连接


def test_backlinks(wiki_dir):
    """backlinks() 返回引用该页面的页面列表"""
    g = WikiGraph(str(wiki_dir))
    g.build()
    # ai.md 被 python.md 和 java.md 引用
    bl = g.backlinks("concepts/ai.md")
    assert "entities/python.md" in bl
    assert "entities/java.md" in bl


def test_degree(wiki_dir):
    """degree() 返回出入度"""
    g = WikiGraph(str(wiki_dir))
    g.build()
    # python.md → ai.md, java.md（out=2），被 ai.md 引用（in=1）
    d = g.degree("entities/python.md")
    assert d["out_degree"] == 2
    assert d["in_degree"] >= 1


def test_degree_nonexistent_node(wiki_dir):
    """被引用但不存在的节点返回正确入度"""
    g = WikiGraph(str(wiki_dir))
    g.build()
    # nonexistent.md 被 ml.md 引用，所以 in_degree=1
    d = g.degree("entities/nonexistent.md")
    assert d["in_degree"] == 1
    assert d["out_degree"] == 0  # 文件不存在，没有出度


# ============================================================================
# to_dict
# ============================================================================


def test_to_dict_structure(wiki_dir):
    """to_dict() 返回正确的结构"""
    g = WikiGraph(str(wiki_dir))
    result = g.to_dict()
    assert "nodes" in result
    assert "edges" in result
    assert "stats" in result
    assert len(result["nodes"]) >= 4
    assert len(result["edges"]) >= 4
    assert result["stats"]["total_nodes"] == len(result["nodes"])
    assert result["stats"]["total_edges"] == len(result["edges"])


def test_to_dict_node_fields(wiki_dir):
    """node 包含 id 和 degree"""
    g = WikiGraph(str(wiki_dir))
    result = g.to_dict()
    for node in result["nodes"]:
        assert "id" in node
        assert "degree" in node
        assert "in" in node["degree"]
        assert "out" in node["degree"]


def test_to_dict_edge_fields(wiki_dir):
    """edge 包含 source 和 target"""
    g = WikiGraph(str(wiki_dir))
    result = g.to_dict()
    for edge in result["edges"]:
        assert "source" in edge
        assert "target" in edge


# ============================================================================
# 边界条件
# ============================================================================


def test_empty_wiki(tmp_path):
    """空目录构建图返回空节点和边"""
    d = tmp_path / "empty"
    d.mkdir()
    g = WikiGraph(str(d))
    g.build()
    assert g.nodes() == []
    assert g.edges() == []


def test_build_called_only_once(wiki_dir):
    """重复调用 build() 重置图"""
    g = WikiGraph(str(wiki_dir))
    g.build()
    first_count = len(g.nodes())

    # 添加新页面
    extra = wiki_dir / "concepts" / "new.md"
    extra.write_text("# New\n", encoding="utf-8")

    g.build()  # 重建
    assert len(g.nodes()) == first_count + 1  # 现在包含新页面
