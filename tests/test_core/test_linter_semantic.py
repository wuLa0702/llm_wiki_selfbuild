"""
LintTool 语义检测单元测试 — Phase 4 Step 5
"""
import json
import time

import pytest

from src.core.linter import LintTool, _SEMANTIC_CACHE, SEMANTIC_CACHE_TTL


@pytest.fixture(autouse=True)
def clear_semantic_cache():
    """每个测试前清空语义缓存，防止测试间干扰"""
    _SEMANTIC_CACHE["result"] = None
    _SEMANTIC_CACHE["expires_at"] = 0
    yield
from src.core.graph import WikiGraph
from src.llm.adapter import LLMError


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def wiki_dir(tmp_path):
    d = tmp_path / "wiki"
    d.mkdir()

    (d / "entities").mkdir()
    (d / "concepts").mkdir()

    # 页面 A
    (d / "entities" / "python.md").write_text(
        "---\ntitle: Python\ntype: entity\n---\n"
        "# Python\n\nPython is a dynamically typed language.",
        encoding="utf-8",
    )
    # 页面 B
    (d / "entities" / "java.md").write_text(
        "---\ntitle: Java\ntype: entity\n---\n"
        "# Java\n\nJava is a statically typed language.",
        encoding="utf-8",
    )
    # 浅页面
    (d / "concepts" / "shallow.md").write_text(
        "---\ntitle: Shallow\ntype: concept\n---\n# Shallow\n\nToo short.",
        encoding="utf-8",
    )
    return d


@pytest.fixture
def linter(wiki_dir):
    return LintTool(str(wiki_dir))


@pytest.fixture
def mock_repo(mocker):
    repo = mocker.MagicMock()
    repo.get_page.side_effect = lambda p: {
        "entities/python.md": {"path": "entities/python.md", "title": "Python", "page_type": "entity", "word_count": 50},
        "entities/java.md": {"path": "entities/java.md", "title": "Java", "page_type": "entity", "word_count": 40},
        "concepts/shallow.md": {"path": "concepts/shallow.md", "title": "Shallow", "page_type": "concept", "word_count": 5},
    }.get(p)
    return repo


# ============================================================================
# _collect_pages_summary
# ============================================================================


def test_collect_pages_summary(linter, mock_repo):
    """_collect_pages_summary 返回页面摘要文本"""
    summary = linter._collect_pages_summary(mock_repo)
    assert "Python" in summary
    assert "Java" in summary
    assert "路径:" in summary
    assert "标题:" in summary
    assert "类型:" in summary


def test_collect_pages_summary_empty(tmp_path):
    """空 wiki 目录返回空字符串"""
    d = tmp_path / "empty"
    d.mkdir()
    l = LintTool(str(d))
    repo = type("R", (), {"get_page": lambda self, p: None})()
    assert l._collect_pages_summary(repo) == ""


# ============================================================================
# check_semantic — LLM 成功
# ============================================================================


def test_check_semantic_returns_structure(linter, mock_repo, mocker):
    """成功调用 LLM 后返回 contradictions/knowledge_gaps/shallow_pages"""
    mock_result = {
        "contradictions": [
            {"page_a": "entities/python.md", "page_b": "entities/java.md",
             "claim_a": "dynamic", "claim_b": "static",
             "description": "type system", "confidence": "high"},
        ],
        "knowledge_gaps": [],
        "shallow_pages": [
            {"page": "concepts/shallow.md", "reason": "too short", "suggestion": "merge"},
        ],
    }
    mock_llm = mocker.MagicMock()
    mock_llm.chat_structured.return_value = mock_result

    result = linter.check_semantic(mock_llm, mock_repo)

    assert not result["cached"]
    assert len(result["contradictions"]) == 1
    assert len(result["shallow_pages"]) == 1
    assert "cached" in result
    assert "summary" in result


def test_check_semantic_passes_operation(linter, mock_repo, mocker):
    """chat_structured 被传入 operation='lint_semantic'"""
    mock_llm = mocker.MagicMock()
    mock_llm.chat_structured.return_value = {"contradictions": [], "knowledge_gaps": [], "shallow_pages": []}

    linter.check_semantic(mock_llm, mock_repo)

    assert mock_llm.chat_structured.call_args[1]["operation"] == "lint_semantic"


# ============================================================================
# check_semantic — 缓存
# ============================================================================


def test_check_semantic_cache_hit(linter, mock_repo, mocker):
    """第二次调用返回缓存结果"""

    mock_llm = mocker.MagicMock()
    mock_llm.chat_structured.return_value = {"contradictions": [], "knowledge_gaps": [], "shallow_pages": []}

    result1 = linter.check_semantic(mock_llm, mock_repo)
    assert not result1["cached"]

    # 第二次调用应命中缓存
    result2 = linter.check_semantic(mock_llm, mock_repo)
    assert result2["cached"]

    # LLM 只被调用了一次
    assert mock_llm.chat_structured.call_count == 1


def test_check_semantic_cache_expires(linter, mock_repo, mocker):
    """TTL 过期后重新调用 LLM"""

    mock_llm = mocker.MagicMock()
    mock_llm.chat_structured.return_value = {"contradictions": [], "knowledge_gaps": [], "shallow_pages": []}

    linter.check_semantic(mock_llm, mock_repo)

    # 手动过期
    _SEMANTIC_CACHE["expires_at"] = time.time() - 1

    linter.check_semantic(mock_llm, mock_repo)
    assert mock_llm.chat_structured.call_count == 2


# ============================================================================
# check_semantic — 异常处理
# ============================================================================


def test_check_semantic_llm_error(linter, mock_repo, mocker):
    """LLM 调用失败时返回降级结果"""
    mock_llm = mocker.MagicMock()
    mock_llm.chat_structured.side_effect = LLMError("LLM timeout")

    result = linter.check_semantic(mock_llm, mock_repo)
    assert result["contradictions"] == []
    assert result["knowledge_gaps"] == []
    assert result["shallow_pages"] == []
    assert "error" in result


def test_check_semantic_empty_pages(linter, mock_repo, mocker):
    """没有页面时直接返回空结果，不调 LLM"""

    # 模拟 repo.get_page 返回 None
    mock_repo2 = mocker.MagicMock()
    mock_repo2.get_page.return_value = None

    # 清空 graph 节点
    empty_dir = linter.wiki_dir + "_nonexistent"
    linter2 = LintTool(empty_dir)

    mock_llm = mocker.MagicMock()
    result = linter2.check_semantic(mock_llm, mock_repo2)

    assert result["contradictions"] == []
    mock_llm.chat_structured.assert_not_called()


# ============================================================================
# integration — compiler.lint(semantic=True)
# ============================================================================


def test_compiler_lint_semantic_flag(mocker):
    """WikiCompiler.lint(semantic=True) 调用 check_semantic"""
    from src.core.wiki_compiler import WikiCompiler

    compiler = WikiCompiler()
    compiler.writer.base_dir = "/tmp/fake"
    compiler.repo = mocker.MagicMock()

    mock_semantic = mocker.patch.object(LintTool, "check_semantic", return_value={"contradictions": []})
    mock_static = mocker.patch.object(LintTool, "run_all", return_value={"health_score": 100})

    # semantic=True
    compiler.lint(semantic=True)
    mock_semantic.assert_called_once()
    mock_static.assert_not_called()

    mock_semantic.reset_mock()

    # semantic=False（默认）
    compiler.lint(semantic=False)
    mock_static.assert_called_once()
