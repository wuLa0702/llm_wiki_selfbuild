"""
LintTool 语义检测单元测试 — Phase 4 Step 5（SQLite 缓存 + 脏标记 + 采样）
"""
import json

import pytest

import src.core.lint.linter
from src.core.lint import LintTool, mark_lint_cache_dirty
from src.llm.adapter import LLMError


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def reset_dirty_flag():
    """每个测试前重置脏标记"""
    src.core.lint.linter._LINT_CACHE_DIRTY = False


@pytest.fixture
def wiki_dir(tmp_path):
    d = tmp_path / "wiki"
    d.mkdir()
    (d / "entities").mkdir()
    (d / "concepts").mkdir()

    (d / "entities" / "python.md").write_text(
        "---\ntitle: Python\ntype: entity\n---\n"
        "# Python\n\nPython is a dynamically typed language.",
        encoding="utf-8",
    )
    (d / "entities" / "java.md").write_text(
        "---\ntitle: Java\ntype: entity\n---\n"
        "# Java\n\nJava is a statically typed language.",
        encoding="utf-8",
    )
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
    # SQLite 缓存默认返回 None（未缓存）
    repo.get_lint_cache.return_value = None
    return repo


# ============================================================================
# _collect_pages_summary
# ============================================================================


def test_collect_pages_summary(linter, mock_repo):
    """_collect_pages_summary 返回页面摘要文本"""
    summary, sampled, total = linter._collect_pages_summary(mock_repo)
    assert "Python" in summary
    assert "Java" in summary
    assert "路径:" in summary
    assert sampled == 3
    assert total == 3


def test_collect_pages_summary_empty(tmp_path):
    """空 wiki 目录返回空"""
    d = tmp_path / "empty"
    d.mkdir()
    l = LintTool(str(d))
    repo = type("R", (), {"get_page": lambda self, p: None})()
    text, sampled, total = l._collect_pages_summary(repo)
    assert text == ""
    assert sampled == 0
    assert total == 0


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

    # 验证缓存被写入 SQLite
    mock_repo.save_lint_cache.assert_called_once()


def test_check_semantic_passes_operation(linter, mock_repo, mocker):
    """chat_structured 被传入 operation='lint_semantic'"""
    mock_llm = mocker.MagicMock()
    mock_llm.chat_structured.return_value = {"contradictions": [], "knowledge_gaps": [], "shallow_pages": []}

    linter.check_semantic(mock_llm, mock_repo)

    assert mock_llm.chat_structured.call_args[1]["operation"] == "lint_semantic"


# ============================================================================
# check_semantic — SQLite 缓存 + 脏标记
# ============================================================================


def test_check_semantic_sqlite_cache_hit(linter, mock_repo, mocker):
    """SQLite 有缓存且不脏时，返回缓存结果"""
    cached_result = {
        "contradictions": [{"page_a": "a.md", "page_b": "b.md", "description": "test", "confidence": "low"}],
        "knowledge_gaps": [],
        "shallow_pages": [],
        "summary": "cached",
    }
    mock_repo.get_lint_cache.return_value = cached_result

    mock_llm = mocker.MagicMock()
    result = linter.check_semantic(mock_llm, mock_repo)

    assert result["cached"] is True
    assert len(result["contradictions"]) == 1
    mock_llm.chat_structured.assert_not_called()


def test_check_semantic_dirty_bypasses_cache(linter, mock_repo, mocker):
    """脏标记为 True 时跳过 SQLite 缓存"""
    # 先有缓存
    mock_repo.get_lint_cache.return_value = {"contradictions": [], "knowledge_gaps": [], "shallow_pages": [], "summary": "cached"}

    # 置脏
    mark_lint_cache_dirty()

    mock_llm = mocker.MagicMock()
    mock_llm.chat_structured.return_value = {"contradictions": [], "knowledge_gaps": [], "shallow_pages": []}

    result = linter.check_semantic(mock_llm, mock_repo)

    assert result["cached"] is False
    # 确认 LLM 被调用了（脏标记跳过了缓存）
    mock_llm.chat_structured.assert_called_once()


def test_check_semantic_clears_dirty_after_run(linter, mock_repo, mocker):
    """LLM 调用后脏标记被清除"""
    mark_lint_cache_dirty()

    mock_llm = mocker.MagicMock()
    mock_llm.chat_structured.return_value = {"contradictions": [], "knowledge_gaps": [], "shallow_pages": []}

    linter.check_semantic(mock_llm, mock_repo)

    assert src.core.lint.linter._LINT_CACHE_DIRTY is False


# ============================================================================
# mark_lint_cache_dirty
# ============================================================================


def test_mark_lint_cache_dirty():
    """mark_lint_cache_dirty 设置全局脏标记"""
    src.core.lint.linter._LINT_CACHE_DIRTY = False
    mark_lint_cache_dirty()
    assert src.core.lint.linter._LINT_CACHE_DIRTY is True


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


def test_check_semantic_empty_pages(linter, mocker):
    """没有页面时直接返回空结果，不调 LLM"""
    empty_dir = linter.wiki_dir + "_nonexistent"
    linter2 = LintTool(empty_dir)
    repo = mocker.MagicMock()
    repo.get_lint_cache.return_value = None

    mock_llm = mocker.MagicMock()
    result = linter2.check_semantic(mock_llm, repo)

    assert result["contradictions"] == []
    mock_llm.chat_structured.assert_not_called()


# ============================================================================
# integration — compiler.lint(semantic=True)
# ============================================================================


def test_compiler_lint_semantic_flag(mocker):
    """WikiCompiler.lint(semantic=True) 调用 check_semantic"""
    from src.core.compiler import WikiCompiler

    compiler = WikiCompiler()
    compiler.writer.base_dir = "/tmp/fake"
    compiler.repo = mocker.MagicMock()

    mock_semantic = mocker.patch.object(LintTool, "check_semantic", return_value={"contradictions": []})
    mock_static = mocker.patch.object(LintTool, "run_all", return_value={"health_score": 100})

    compiler.lint(semantic=True)
    mock_semantic.assert_called_once()
    mock_static.assert_not_called()

    mock_semantic.reset_mock()

    compiler.lint(semantic=False)
    mock_static.assert_called_once()


# ============================================================================
# 采样测试
# ============================================================================


def test_sampling_within_limit(tmp_path, mocker):
    """页面数未超过 MAX_SEMANTIC_PAGES 时不采样"""
    d = tmp_path / "wiki"
    d.mkdir()
    for i in range(10):
        (d / f"page{i}.md").write_text(f"---\ntitle: P{i}\ntype: entity\n---\n# P{i}\nContent.", encoding="utf-8")

    l = LintTool(str(d))
    repo = mocker.MagicMock()
    repo.get_page.return_value = {"title": "test", "page_type": "entity", "word_count": 10}

    text, sampled, total = l._collect_pages_summary(repo)
    assert sampled == 10
    assert total == 10
    assert text.count("路径:") == 10
