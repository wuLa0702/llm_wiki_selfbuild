"""
WikiCompiler 单元测试 — Phase 2 两步 CoT + 导航文件
"""
import json
import os

import pytest

from src.core.compiler import CompilerError, WikiCompiler
from src.llm.adapter import LLMError


# ---------------------------------------------------------------------------
# Helpers
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
    c.cache.sources_dir = str(tmp_path / "raw" / "sources")
    c.cache.db_path = str(tmp_path / "wiki.db")
    c.cache._init_table()
    return c


def _mock_cot(mocker, compiler, analysis=None, generate=None):
    """便捷 helper：mock chat_structured(Step1) + chat_template(Step2) + _update_overview"""
    mocker.patch.object(
        compiler.llm, "chat_structured",
        return_value=analysis or MOCK_ANALYSIS,
    )
    mocker.patch.object(
        compiler.llm, "chat_template",
        return_value=generate or MOCK_GENERATE_RESPONSE,
    )
    # 阻止 overview 调用真实 LLM
    mocker.patch.object(compiler, "_update_overview")


# ============================================================================
# 两步 CoT — 成功路径
# ============================================================================


def test_ingest_two_step_creates_pages(compiler, mocker):
    _mock_cot(mocker, compiler)
    result = compiler.ingest("test.md")
    assert result["status"] == "success"
    assert "entities/python.md" in result["pages_created"]
    assert os.path.exists(os.path.join(compiler.writer.base_dir, "entities", "python.md"))


def test_ingest_two_step_records_links(compiler, mocker):
    _mock_cot(mocker, compiler)
    compiler.ingest("test.md")
    page = compiler.repo.get_page("entities/python.md")
    assert "concepts/ai.md" in page["links"]


# ============================================================================
# Step 1 / Step 2 异常
# ============================================================================


def test_ingest_step1_parse_error_fallback(compiler, mocker):
    mock_structured = mocker.patch.object(
        compiler.llm, "chat_structured",
        side_effect=LLMError("Failed to parse structured output: invalid JSON"),
    )
    mock_chat = mocker.patch.object(compiler.llm, "chat", return_value=MOCK_GENERATE_RESPONSE)
    mocker.patch.object(compiler, "_update_overview")

    result = compiler.ingest("test.md")
    assert result["status"] == "success"
    assert mock_structured.call_count == 1
    assert mock_chat.call_count == 1


def test_ingest_step1_llm_error_retry_succeeds(compiler, mocker):
    mocker.patch.object(
        compiler.llm, "chat_structured",
        side_effect=[LLMError("LLM call failed: timeout"), MOCK_ANALYSIS],
    )
    mocker.patch.object(compiler.llm, "chat_template", return_value=MOCK_GENERATE_RESPONSE)
    mocker.patch.object(compiler, "_update_overview")

    result = compiler.ingest("test.md")
    assert result["status"] == "success"


def test_ingest_step1_llm_error_retry_exhausted(compiler, mocker):
    mocker.patch.object(
        compiler.llm, "chat_structured",
        side_effect=[LLMError("t1"), LLMError("t2")],
    )
    mocker.patch.object(compiler.llm, "chat", return_value=MOCK_GENERATE_RESPONSE)
    mocker.patch.object(compiler, "_update_overview")

    result = compiler.ingest("test.md")
    assert result["status"] == "success"


def test_ingest_step2_empty_output(compiler, mocker):
    mocker.patch.object(compiler.llm, "chat_structured", return_value=MOCK_ANALYSIS)
    mocker.patch.object(compiler.llm, "chat_template", return_value="no pages")
    mocker.patch.object(compiler.llm, "chat", return_value=MOCK_GENERATE_RESPONSE)
    mocker.patch.object(compiler, "_update_overview")

    result = compiler.ingest("test.md")
    assert result["status"] == "success"


def test_ingest_step2_llm_error_retry_then_raise(compiler, mocker):
    mocker.patch.object(compiler.llm, "chat_structured", return_value=MOCK_ANALYSIS)
    mocker.patch.object(
        compiler.llm, "chat_template",
        side_effect=[LLMError("g1"), LLMError("g2")],
    )

    with pytest.raises(LLMError, match="g2"):
        compiler.ingest("test.md")


# ============================================================================
# ingest_simple() — Phase 1 兼容
# ============================================================================


def test_ingest_simple_creates_pages(compiler, mocker):
    mocker.patch.object(compiler.llm, "chat", return_value=MOCK_GENERATE_RESPONSE)
    mocker.patch.object(compiler, "_update_overview")
    result = compiler.ingest_simple("test.md")
    assert result["status"] == "success"


# ============================================================================
# 导航文件 — 第三步
# ============================================================================


def test_update_index_creates_file(compiler, mocker):
    """_update_index() 创建 wiki/index.md"""
    _mock_cot(mocker, compiler)
    compiler.ingest("test.md")

    # 手动调用（ingest 里已调过，但被 mock 了）
    compiler._update_index()
    idx = os.path.join(compiler.writer.base_dir, "index.md")
    content = open(idx, encoding="utf-8").read()
    assert "# Wiki 全局索引" in content
    assert "entities/python.md" in content


def test_update_log_format(compiler, mocker):
    """log.md 标题在顶部，条目在下方"""
    _mock_cot(mocker, compiler)
    compiler.ingest("test.md")

    compiler._update_log("test.md", {"entities/x.md": "# X\ncontent"})
    log_path = os.path.join(compiler.writer.base_dir, "log.md")
    content = open(log_path, encoding="utf-8").read()
    # 标题必须在最开头
    assert content.startswith("# Wiki 操作日志")
    # 条目在标题之后
    assert "[2026" in content or "[2025" in content


def test_update_log_appends_above_old(compiler, mocker):
    """新条目插入标题后、旧内容之前"""
    _mock_cot(mocker, compiler)
    compiler.ingest("test.md")

    compiler._update_log("first.md", {"entities/a.md": ""})
    compiler._update_log("second.md", {"entities/b.md": ""})
    log = open(os.path.join(compiler.writer.base_dir, "log.md"), encoding="utf-8").read()
    # 标题在最顶部
    assert log.startswith("# Wiki 操作日志")
    # second（后写入）在 first（先写入）前面（新条目插在前面）
    pos2 = log.index("ingest | second.md")
    pos1 = log.index("ingest | first.md")
    assert pos2 < pos1


def test_update_overview_skips_if_no_index(compiler):
    """index.md 不存在时跳过 overview 生成"""
    compiler._update_overview()
    assert not os.path.exists(os.path.join(compiler.writer.base_dir, "overview.md"))


def test_update_overview_handles_llm_error(compiler, mocker):
    """LLM 失败时写入降级内容"""
    # 先创建 index（跳过校验）
    compiler.writer.write_page("index.md", "# Index\n- entities/python.md", validate=False)
    mocker.patch.object(compiler.llm, "chat", side_effect=LLMError("fail"))

    compiler._update_overview()
    overview = open(os.path.join(compiler.writer.base_dir, "overview.md"), encoding="utf-8").read()
    assert "LLM 生成综述失败" in overview


# ============================================================================
# 边界 / 错误
# ============================================================================


def test_ingest_source_not_found(compiler):
    with pytest.raises(CompilerError, match="Source file not found"):
        compiler.ingest("nonexistent.md")


def test_ingest_empty_source(compiler):
    open(os.path.join(compiler.reader.base_dir, "sources", "empty.md"), "w").write("")
    result = compiler.ingest("empty.md")
    assert result["status"] == "success"
    assert result["pages_created"] == []


# ============================================================================
# 第六步 — 配置与质量信号
# ============================================================================


def test_extract_confidence_summary():
    """_extract_confidence_summary 正确统计置信度"""
    pages = {
        "a.md": "---\nconfidence: high\n---\n# A\n[[b.md]]",
        "b.md": "---\nconfidence: medium\n---\n# B\n[[a.md]]",
        "c.md": "---\nconfidence: high\n---\n# C\n[[d.md]]",
    }
    result = WikiCompiler._extract_confidence_summary(pages)
    assert result == {"high": 2, "medium": 1}


def test_extract_confidence_summary_empty():
    """无页面时返回空字典"""
    assert WikiCompiler._extract_confidence_summary({}) == {}


def test_purpose_md_exists():
    """purpose.md 存在且非空"""
    assert os.path.isfile("purpose.md"), "purpose.md not found"
    content = open("purpose.md", encoding="utf-8").read()
    assert len(content) > 100


def test_ingest_truncates_long_source(compiler, mocker):
    """max_source_chars 截断超长源文件"""
    src = os.path.join(compiler.reader.base_dir, "sources", "long.md")
    with open(src, "w", encoding="utf-8") as f:
        f.write("A" * 5000 + "\n有效内容 [[concepts/ai.md]]。")

    mocker.patch.object(compiler.llm, "chat_structured", return_value=MOCK_ANALYSIS)
    mocker.patch.object(compiler.llm, "chat_template", return_value=MOCK_GENERATE_RESPONSE)
    mocker.patch.object(compiler, "_update_overview")

    result = compiler.ingest("long.md", max_source_chars=500)
    assert result["status"] == "success"
    prompt = compiler.llm.chat_structured.call_args[1]["prompt"]
    assert "内容截断" in prompt
    assert len(prompt) < 3000


# ============================================================================
# SHA256 增量缓存
# ============================================================================


def test_ingest_cache_skips_on_repeat(compiler, mocker):
    """同一文件连续 ingest 两次 → 第二次返回 skipped"""
    mocker.patch.object(compiler.llm, "chat_structured", return_value=MOCK_ANALYSIS)
    mocker.patch.object(compiler.llm, "chat_template", return_value=MOCK_GENERATE_RESPONSE)
    mocker.patch.object(compiler, "_update_overview")

    result1 = compiler.ingest("test.md")
    assert result1["status"] == "success"

    result2 = compiler.ingest("test.md")
    assert result2["status"] == "skipped"


def test_ingest_cache_processes_after_modification(compiler, mocker):
    """修改文件后再次 ingest → 正常处理"""
    mocker.patch.object(compiler.llm, "chat_structured", return_value=MOCK_ANALYSIS)
    mocker.patch.object(compiler.llm, "chat_template", return_value=MOCK_GENERATE_RESPONSE)
    mocker.patch.object(compiler, "_update_overview")

    compiler.ingest("test.md")

    # 修改文件
    src = os.path.join(compiler.reader.base_dir, "sources", "test.md")
    with open(src, "w", encoding="utf-8") as f:
        f.write("修改后的内容")

    result = compiler.ingest("test.md")
    assert result["status"] == "success"
    assert len(result["pages_updated"]) > 0


def test_ingest_cache_marks_after_simple(compiler, mocker):
    """降级到 simple 后也缓存"""
    mocker.patch.object(compiler.llm, "chat_structured",
                        side_effect=LLMError("Failed to parse: bad json"))
    mocker.patch.object(compiler.llm, "chat", return_value=MOCK_GENERATE_RESPONSE)
    mocker.patch.object(compiler, "_update_overview")

    compiler.ingest("test.md")  # 降级到 simple

    result = compiler.ingest("test.md")  # 第二次应跳过
    assert result["status"] == "skipped"


# ============================================================================
# Token 用量集成
# ============================================================================


def test_ingest_returns_token_usage(compiler, mocker):
    """两步 CoT ingest 返回 token_usage"""
    import json

    mock_llm = mocker.MagicMock()
    mock_response1 = mocker.MagicMock()
    mock_response1.content = json.dumps(MOCK_ANALYSIS)
    mock_response1.response_metadata = {
        "token_usage": {"prompt_tokens": 80, "completion_tokens": 20, "total_tokens": 100},
    }
    mock_response2 = mocker.MagicMock()
    mock_response2.content = MOCK_GENERATE_RESPONSE
    mock_response2.response_metadata = {
        "token_usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
    }
    mock_llm.invoke.side_effect = [mock_response1, mock_response2]
    compiler.llm._llm = mock_llm

    mocker.patch.object(compiler, "_update_overview")

    result = compiler.ingest("test.md")
    assert result["status"] == "success"
    assert result["token_usage"] is not None
    assert result["token_usage"]["step1_input"] == 80
    assert result["token_usage"]["step1_output"] == 20
    assert result["token_usage"]["step2_input"] == 200
    assert result["token_usage"]["step2_output"] == 100
    assert result["token_usage"]["total"] == 400  # 80+20 + 200+100


def test_ingest_simple_returns_token_usage(compiler, mocker):
    """ingest_simple 也返回 token_usage"""
    mock_llm = mocker.MagicMock()
    mock_response = mocker.MagicMock()
    mock_response.content = MOCK_GENERATE_RESPONSE
    mock_response.response_metadata = {
        "token_usage": {"prompt_tokens": 50, "completion_tokens": 25, "total_tokens": 75},
    }
    mock_llm.invoke.return_value = mock_response
    compiler.llm._llm = mock_llm

    mocker.patch.object(compiler, "_update_overview")

    result = compiler.ingest_simple("test.md")
    assert result["status"] == "success"
    assert result["token_usage"] is not None
    assert result["token_usage"]["step1_input"] == 50
    assert result["token_usage"]["step1_output"] == 25


# ============================================================================
# WikiGraph 集成
# ============================================================================


def test_ingest_builds_graph(compiler, mocker):
    """ingest 后 graph 被构建且包含新页面"""
    _mock_cot(mocker, compiler)
    compiler.graph.wiki_dir = compiler.writer.base_dir

    compiler.ingest("test.md")
    nodes = compiler.graph.nodes()
    assert "entities/python.md" in nodes
    assert "concepts/ai.md" in nodes


# ============================================================================
# Query 答案归档 — 索引与图更新
# ============================================================================


def test_query_archive_updates_index(compiler, mocker):
    """query 归档后自动更新 index 和 invalidate 图"""
    mocker.patch.object(
        compiler.query_engine, "query",
        return_value={
            "answer": "Python 是一种编程语言。",
            "sources": ["entities/python.md"],
            "confidence": "high",
            "gaps": [],
            "archived": "queries/python-shi-shi.md",
        },
    )
    index_spy = mocker.spy(compiler, "_update_index")
    invalidate_spy = mocker.spy(compiler.graph, "invalidate")

    result = compiler.query("Python 是什么？", archive=True)

    assert result["archived"] == "queries/python-shi-shi.md"
    index_spy.assert_called_once()
    invalidate_spy.assert_called_once()


def test_query_no_archive_skips_update(compiler, mocker):
    """query 不归档时跳过 index 和 graph 更新"""
    mocker.patch.object(
        compiler.query_engine, "query",
        return_value={
            "answer": "Python 是一种编程语言。",
            "sources": ["entities/python.md"],
            "confidence": "high",
            "gaps": [],
            "archived": None,
        },
    )
    index_spy = mocker.spy(compiler, "_update_index")
    invalidate_spy = mocker.spy(compiler.graph, "invalidate")

    compiler.query("Python 是什么？", archive=False)

    index_spy.assert_not_called()
    invalidate_spy.assert_not_called()

