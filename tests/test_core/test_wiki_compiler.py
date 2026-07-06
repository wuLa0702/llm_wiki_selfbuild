"""
WikiCompiler 单元测试 — Phase 2 两步 CoT + chat_structured
"""
import json
import os

import pytest

from src.core.wiki_compiler import CompilerError, WikiCompiler
from src.llm.adapter import LLMError


# ---------------------------------------------------------------------------
# Fixtures & Helpers
# ---------------------------------------------------------------------------

MOCK_ANALYSIS = {
    "entities": [{"name": "Python", "type": "tool", "importance": "high"}],
    "concepts": [{"name": "人工智能", "description": "AI", "related_to": ["Python"], "importance": "high"}],
    "contradictions": [],
    "connections_to_existing": [],
    "recommendations": [],
}

MOCK_GENERATE_RESPONSE = """---PAGE:entities/python.md---
---
title: "Python"
type: entity
tags: [编程语言]
---
# Python

Python 用于 [[concepts/ai.md|人工智能]]。
---END---
---PAGE:concepts/ai.md---
---
title: "人工智能"
type: concept
tags: [AI]
---
# 人工智能

AI 常用 [[entities/python.md|Python]]。
---END---"""


@pytest.fixture
def compiler(tmp_path):
    """创建指向 tmp_path 的 WikiCompiler"""
    (tmp_path / "raw" / "sources").mkdir(parents=True)
    (tmp_path / "wiki").mkdir()
    (tmp_path / "raw" / "sources" / "test.md").write_text(
        "Python 是一门编程语言，广泛用于 AI 开发。", encoding="utf-8"
    )

    c = WikiCompiler()
    c.reader.base_dir = str(tmp_path / "raw")
    c.writer.base_dir = str(tmp_path / "wiki")
    c.repo.db_path = str(tmp_path / "wiki.db")
    c.repo._init_db()
    return c


def _mock_cot(mocker, compiler, analysis=None, generate=None):
    """便捷 helper：同时 mock chat_structured(Step1) + chat_template(Step2)"""
    if analysis is None:
        analysis = MOCK_ANALYSIS
    if generate is None:
        generate = MOCK_GENERATE_RESPONSE
    mocker.patch.object(compiler.llm, "chat_structured", return_value=analysis)
    mocker.patch.object(compiler.llm, "chat_template", return_value=generate)


# ============================================================================
# 两步 CoT — 成功路径
# ============================================================================


def test_ingest_two_step_creates_pages(compiler, mocker):
    """Step 1 chat_structured + Step 2 chat_template → 页面创建"""
    _mock_cot(mocker, compiler)
    result = compiler.ingest("test.md")
    assert result["status"] == "success"
    assert "entities/python.md" in result["pages_created"]
    assert os.path.exists(os.path.join(compiler.writer.base_dir, "entities", "python.md"))


def test_ingest_two_step_records_links(compiler, mocker):
    """双向链接正确记录"""
    _mock_cot(mocker, compiler)
    compiler.ingest("test.md")
    page = compiler.repo.get_page("entities/python.md")
    assert "concepts/ai.md" in page["links"]


# ============================================================================
# Step 1 异常 → 降级
# ============================================================================


def test_ingest_step1_parse_error_fallback(compiler, mocker):
    """JSON 解析失败 → 直接降级（不重试）"""
    mock_structured = mocker.patch.object(
        compiler.llm, "chat_structured",
        side_effect=LLMError("Failed to parse structured output: invalid JSON"),
    )
    mock_chat = mocker.patch.object(compiler.llm, "chat", return_value=MOCK_GENERATE_RESPONSE)

    result = compiler.ingest("test.md")
    assert result["status"] == "success"
    assert mock_structured.call_count == 1  # 格式错误，不重试
    assert mock_chat.call_count == 1


def test_ingest_step1_llm_error_retry_succeeds(compiler, mocker):
    """第一次超时，重试成功"""
    mock_structured = mocker.patch.object(
        compiler.llm, "chat_structured",
        side_effect=[LLMError("LLM call failed: timeout"), MOCK_ANALYSIS],
    )
    mock_template = mocker.patch.object(
        compiler.llm, "chat_template", return_value=MOCK_GENERATE_RESPONSE,
    )

    result = compiler.ingest("test.md")
    assert result["status"] == "success"
    assert mock_structured.call_count == 2  # 一次失败 + 一次成功
    assert mock_template.call_count == 1


def test_ingest_step1_llm_error_retry_exhausted(compiler, mocker):
    """重试后仍失败 → 降级 simple"""
    mock_structured = mocker.patch.object(
        compiler.llm, "chat_structured",
        side_effect=[LLMError("timeout1"), LLMError("timeout2")],
    )
    mock_chat = mocker.patch.object(compiler.llm, "chat", return_value=MOCK_GENERATE_RESPONSE)

    result = compiler.ingest("test.md")
    assert result["status"] == "success"
    assert mock_structured.call_count == 2
    assert mock_chat.call_count == 1


# ============================================================================
# Step 2 异常
# ============================================================================


def test_ingest_step2_empty_output_fallback(compiler, mocker):
    """Step 2 无有效页面 → 降级（不重试）"""
    mock_structured = mocker.patch.object(
        compiler.llm, "chat_structured", return_value=MOCK_ANALYSIS,
    )
    mock_template = mocker.patch.object(
        compiler.llm, "chat_template", return_value="没有生成任何页面。",
    )
    mock_chat = mocker.patch.object(compiler.llm, "chat", return_value=MOCK_GENERATE_RESPONSE)

    result = compiler.ingest("test.md")
    assert result["status"] == "success"
    assert mock_template.call_count == 1  # 无重试
    assert mock_chat.call_count == 1


def test_ingest_step2_llm_error_retry_then_raise(compiler, mocker):
    """Step 2 重试仍失败 → 抛出"""
    mocker.patch.object(compiler.llm, "chat_structured", return_value=MOCK_ANALYSIS)
    mocker.patch.object(
        compiler.llm, "chat_template",
        side_effect=[LLMError("gen1"), LLMError("gen2")],
    )

    with pytest.raises(LLMError, match="gen2"):
        compiler.ingest("test.md")


# ============================================================================
# ingest_simple() — Phase 1 兼容
# ============================================================================


def test_ingest_simple_creates_pages(compiler, mocker):
    mocker.patch.object(compiler.llm, "chat", return_value=MOCK_GENERATE_RESPONSE)
    result = compiler.ingest_simple("test.md")
    assert result["status"] == "success"


# ============================================================================
# 边界 / 错误
# ============================================================================


def test_ingest_source_not_found(compiler):
    with pytest.raises(CompilerError, match="Source file not found"):
        compiler.ingest("nonexistent.md")


def test_ingest_empty_source(compiler):
    empty_path = os.path.join(compiler.reader.base_dir, "sources", "empty.md")
    open(empty_path, "w", encoding="utf-8").write("")
    result = compiler.ingest("empty.md")
    assert result["status"] == "success"
    assert result["pages_created"] == []
