"""
QueryEngine 单元测试 — Phase 3 Step 4
"""
import json
import os

import pytest

from src.core.query import QueryEngine
from src.llm.adapter import LLMError


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def wiki_dir(tmp_path):
    """创建含页面的测试 wiki 目录"""
    d = tmp_path / "wiki"
    d.mkdir()

    (d / "entities").mkdir()
    (d / "concepts").mkdir()
    (d / "queries").mkdir()

    # 创建几个测试页面
    (d / "entities" / "python.md").write_text(
        "---\ntitle: Python\ntype: entity\ntags: [编程语言]\n---\n"
        "# Python\n\nPython 是一种解释型编程语言。\n"
        "常用于 AI 开发。\n\n参见 [[concepts/ai.md|AI]]。",
        encoding="utf-8",
    )
    (d / "concepts" / "ai.md").write_text(
        "---\ntitle: 人工智能\ntype: concept\n---\n"
        "# 人工智能\n\nAI 是计算机科学的重要分支。\n"
        "常用语言包括 [[entities/python.md|Python]]。",
        encoding="utf-8",
    )
    # index.md
    (d / "index.md").write_text(
        "# Index\n\n- [[entities/python.md]]\n- [[concepts/ai.md]]",
        encoding="utf-8",
    )
    return d


@pytest.fixture
def repo(tmp_path, mocker):
    """Mock WikiRepository"""
    from src.db.repository import WikiRepository

    r = WikiRepository(str(tmp_path / "wiki.db"))
    r.add_page("entities/python.md", "Python", "entity", ["编程语言"])
    r.add_page("concepts/ai.md", "人工智能", "concept", ["AI"])
    return r


@pytest.fixture
def search_tool(mocker):
    """Mock SearchTool"""
    st = mocker.MagicMock()
    st.search.return_value = [
        {"path": "entities/python.md", "title": "Python", "match_type": "title"},
    ]
    return st


@pytest.fixture
def graph(wiki_dir):
    """真实 WikiGraph 实例（用测试目录）"""
    from src.core.graph import WikiGraph

    g = WikiGraph(str(wiki_dir))
    g.build()
    return g


@pytest.fixture
def llm(mocker):
    """Mock LLMAdapter"""
    llm = mocker.MagicMock()
    llm.last_usage = None
    llm.chat_structured.return_value = {
        "answer": "Python 是一种编程语言，广泛用于 AI。参见 [[entities/python.md|Python]]。",
        "confidence": "high",
        "gaps": [],
    }
    return llm


@pytest.fixture
def writer(wiki_dir):
    """WriteTool 指向测试 wiki 目录"""
    from src.tools.write_tool import WriteTool

    w = WriteTool()
    w.base_dir = str(wiki_dir)
    return w


@pytest.fixture
def engine(repo, search_tool, graph, llm, writer):
    """QueryEngine 实例"""
    return QueryEngine(repo=repo, search_tool=search_tool, graph=graph, llm=llm, writer=writer)


# ============================================================================
# query() — 正常路径
# ============================================================================


def test_query_returns_answer(engine):
    """正常查询返回带引用的答案"""
    result = engine.query("Python 是什么？")
    assert "answer" in result
    assert len(result["answer"]) > 0
    assert "sources" in result
    assert result["confidence"] == "high"


def test_query_sources_are_paths(engine):
    """sources 列表包含 wiki 页面路径"""
    result = engine.query("Python 是什么？")
    assert len(result["sources"]) > 0
    for s in result["sources"]:
        assert s.endswith(".md")  # 允许 index.md（无子目录前缀）


def test_query_empty_knowledge_base(engine, search_tool):
    """知识库无匹配时返回低置信度回答"""
    search_tool.search.return_value = []
    engine.repo.search_pages = lambda q, limit=20: []

    result = engine.query("不存在的主题")
    assert result["confidence"] == "low"
    assert "暂无相关内容" in result["answer"] or len(result["sources"]) == 0


# ============================================================================
# query() — 图扩展
# ============================================================================


def test_query_graph_expansion(engine, search_tool):
    """图扩展能找到不含关键词但被关联的页面"""
    # 只返回 python.md（不含关键词 "AI"）
    search_tool.search.return_value = [
        {"path": "entities/python.md", "title": "Python", "match_type": "title"},
    ]
    engine.repo.search_pages = lambda q, limit=20: []

    result = engine.query("AI 相关概念")
    # 图扩展应能找到 concepts/ai.md（python.md 链接到 ai.md）
    assert "concepts/ai.md" in result["sources"]


def test_query_graph_depth2(engine, search_tool, wiki_dir):
    """depth=1 的图扩展足够发现直接关联"""
    search_tool.search.return_value = [
        {"path": "entities/python.md", "title": "Python", "match_type": "title"},
    ]
    engine.repo.search_pages = lambda q, limit=20: []

    result = engine.query("编程语言")
    # python.md 的邻居包括 ai.md（通过 wikilink）
    assert "concepts/ai.md" in result["sources"]


# ====================================================================
# query() — 归档
# ====================================================================


def test_query_archive_creates_file(engine, wiki_dir):
    """archive=True 时生成 wiki/queries/ 下的文件"""
    result = engine.query("Python 是什么？", archive=True)
    assert result["archived"] is not None
    assert result["archived"].startswith("queries/")
    archived_path = os.path.join(wiki_dir, result["archived"])
    assert os.path.isfile(archived_path)


def test_query_archive_has_frontmatter(engine, wiki_dir):
    """归档文件包含 YAML frontmatter"""
    result = engine.query("Python 是什么？", archive=True)
    path = os.path.join(wiki_dir, result["archived"])
    content = open(path, encoding="utf-8").read()
    assert content.startswith("---")
    assert "title:" in content
    assert "type: query" in content


def test_query_archive_skips_low_confidence(engine, llm):
    """低置信度回答不归档"""
    llm.chat_structured.return_value = {
        "answer": "我不确定...",
        "confidence": "low",
        "gaps": ["信息不足"],
    }
    result = engine.query("Python", archive=True)
    assert result["archived"] is None


def test_query_archive_skips_empty_answer(engine, llm):
    """空回答不归档"""
    llm.chat_structured.return_value = {
        "answer": "",
        "confidence": "medium",
        "gaps": [],
    }
    result = engine.query("Python", archive=True)
    assert result["archived"] is None


# ====================================================================
# query() — 异常处理
# ====================================================================


def test_query_llm_failure_fallback(engine, llm):
    """LLM 调用失败返回降级回答"""
    llm.chat_structured.side_effect = LLMError("API timeout")

    result = engine.query("Python 是什么？")
    assert result["confidence"] == "low"
    assert "LLM 调用失败" in result["answer"]


# ====================================================================
# _question_to_slug
# ====================================================================


def test_question_to_slug_simple():
    """普通问题生成合法 slug"""
    slug = QueryEngine._question_to_slug("Python 是什么？")
    assert "python" in slug
    assert slug == "python-是什么"


def test_question_to_slug_long():
    """长问题截取前 30 字符"""
    slug = QueryEngine._question_to_slug("a" * 50)
    assert len(slug) <= 30


def test_question_to_slug_special_chars():
    """特殊字符替换为连字符"""
    slug = QueryEngine._question_to_slug("What is AI? #deeplearning")
    assert "<" not in slug
    assert "?" not in slug
    assert "#" not in slug


def test_question_to_slug_fallback():
    """全特殊字符时返回默认值"""
    slug = QueryEngine._question_to_slug("???!!!")
    assert slug == "query"


# ====================================================================
# _strip_frontmatter
# ====================================================================


def test_strip_frontmatter_removes_yaml():
    """YAML frontmatter 被去除"""
    content = "---\ntitle: Test\n---\n# Body"
    assert QueryEngine._strip_frontmatter(content) == "# Body"


def test_strip_frontmatter_no_frontmatter():
    """无 frontmatter 返回原内容"""
    assert QueryEngine._strip_frontmatter("# No frontmatter") == "# No frontmatter"


# ====================================================================
# _llm_suggest_pages
# ====================================================================


def test_llm_suggest_pages_empty_if_no_index(engine, wiki_dir):
    """index.md 不存在时返回空列表"""
    os.remove(os.path.join(wiki_dir, "index.md"))
    result = engine._llm_suggest_pages("Python")
    assert result == []


# ====================================================================
# _locate_candidates
# ====================================================================


def test_locate_candidates_deduplicates(engine):
    """定位函数去重"""
    candidates = engine._locate_candidates("Python", limit=10)
    # python.md 可能被 SQLite 和 SearchTool 同时匹配
    assert len(candidates) == len(set(candidates))


def test_locate_candidates_respects_limit(engine):
    """候选页不超过 limit"""
    candidates = engine._locate_candidates("Python", limit=1)
    assert len(candidates) <= 1


# ====================================================================
# _build_context
# ====================================================================


def test_build_context_includes_content(engine):
    """上下文包含页面正文（不含 frontmatter）"""
    context = engine._build_context(["entities/python.md"])
    assert "Python 是一种" in context
    assert "---" not in context.split("---PAGE:")[1].split("---")[0] if "---PAGE:" in context else True


def test_build_context_missing_file(engine):
    """不存在的文件静默跳过"""
    context = engine._build_context(["entities/nonexistent.md"])
    assert "暂无相关页面" in context


# ====================================================================
# 集成 — POST /v1/query API
# ====================================================================


def test_query_api_endpoint(client, mocker):
    """POST /v1/query 返回正确 JSON"""
    # Mock WikiCompiler.query()
    mock_query = mocker.patch("src.api.routes.misc.WikiCompiler.query")
    mock_query.return_value = {
        "answer": "Python 是编程语言。",
        "sources": ["entities/python.md"],
        "confidence": "high",
        "gaps": [],
        "archived": None,
    }

    response = client.post(
        "/v1/query",
        json={"question": "Python 是什么？", "archive": False},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["answer"] == "Python 是编程语言。"
    assert data["confidence"] == "high"
    assert "entities/python.md" in data["sources"]


def test_query_api_archive_true(client, mocker):
    """archive=True 传给 query engine"""
    mock_query = mocker.patch("src.api.routes.misc.WikiCompiler.query")
    mock_query.return_value = {
        "answer": "测试回答",
        "sources": ["entities/python.md"],
        "confidence": "high",
        "gaps": [],
        "archived": "queries/test.md",
    }

    response = client.post(
        "/v1/query",
        json={"question": "测试", "archive": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["archived"] == "queries/test.md"


def test_query_api_empty_question(client):
    """空问题返回 422（Pydantic min_length 校验）"""
    response = client.post(
        "/v1/query",
        json={"question": ""},
    )
    assert response.status_code == 422
