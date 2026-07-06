"""
WikiCompiler 单元测试
"""
import os

import pytest

from src.core.wiki_compiler import CompilerError, WikiCompiler
from src.llm.adapter import LLMError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MOCK_LLM_RESPONSE = """---PAGE:entities/python.md---
# Python

Python 是一种解释型编程语言。

常用于 [[concepts/ai.md|人工智能]] 开发。
---END---
---PAGE:concepts/ai.md---
# 人工智能

AI 是计算机科学分支，[[entities/python.md|Python]] 是常用语言。
#AI #编程
---END---
"""


@pytest.fixture
def compiler(tmp_path, mocker):
    """创建 WikiCompiler，工具和数据库均指向 tmp_path"""
    # 创建目录结构
    (tmp_path / "raw" / "sources").mkdir(parents=True)
    (tmp_path / "wiki").mkdir()

    # 创建测试源文件
    (tmp_path / "raw" / "sources" / "test.md").write_text(
        "Python 是一门编程语言，广泛用于 AI 开发。", encoding="utf-8"
    )

    c = WikiCompiler()

    # 重定向所有路径到 tmp_path
    c.reader.base_dir = str(tmp_path / "raw")
    c.writer.base_dir = str(tmp_path / "wiki")
    c.repo.db_path = str(tmp_path / "wiki.db")
    c.repo._init_db()

    return c


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------


def test_ingest_creates_pages(compiler, mocker):
    """Ingest 后 wiki/ 目录下创建了对应页面"""
    mocker.patch.object(compiler.llm, "chat", return_value=MOCK_LLM_RESPONSE)

    result = compiler.ingest("test.md")

    assert result["status"] == "success"
    assert "entities/python.md" in result["pages_created"]
    assert "concepts/ai.md" in result["pages_created"]

    # 验证文件确实写入了
    wiki_python = os.path.join(compiler.writer.base_dir, "entities", "python.md")
    wiki_ai = os.path.join(compiler.writer.base_dir, "concepts", "ai.md")
    assert os.path.exists(wiki_python)
    assert os.path.exists(wiki_ai)
    assert "Python" in open(wiki_python, encoding="utf-8").read()


def test_ingest_records_db_metadata(compiler, mocker):
    """Ingest 后数据库中有对应记录"""
    mocker.patch.object(compiler.llm, "chat", return_value=MOCK_LLM_RESPONSE)

    compiler.ingest("test.md")

    page = compiler.repo.get_page("entities/python.md")
    assert page is not None
    assert page["title"] == "Python"
    assert page["page_type"] == "entity"


def test_ingest_records_links(compiler, mocker):
    """Ingest 后双向链接被正确记录"""
    mocker.patch.object(compiler.llm, "chat", return_value=MOCK_LLM_RESPONSE)

    compiler.ingest("test.md")

    python_page = compiler.repo.get_page("entities/python.md")
    ai_page = compiler.repo.get_page("concepts/ai.md")

    assert "concepts/ai.md" in python_page["links"]
    assert "entities/python.md" in ai_page["backlinks"]


def test_ingest_writes_log(compiler, mocker):
    """Ingest 后 wiki/log.md 被更新"""
    mocker.patch.object(compiler.llm, "chat", return_value=MOCK_LLM_RESPONSE)

    compiler.ingest("test.md")

    log_path = os.path.join(compiler.writer.base_dir, "log.md")
    assert os.path.exists(log_path)
    log_content = open(log_path, encoding="utf-8").read()
    assert "test.md" in log_content
    assert "entities/python.md" in log_content


def test_ingest_updates_existing_page(compiler, mocker):
    """已存在的页面被更新而非重复创建"""
    mocker.patch.object(compiler.llm, "chat", return_value=MOCK_LLM_RESPONSE)

    # 第一次 ingest
    compiler.ingest("test.md")
    assert "entities/python.md" not in compiler.ingest("test.md")["pages_created"]

    result = compiler.ingest("test.md")
    assert "entities/python.md" in result["pages_updated"]
    assert "concepts/ai.md" in result["pages_updated"]


# ---------------------------------------------------------------------------
# 边界 / 错误
# ---------------------------------------------------------------------------


def test_ingest_empty_source(compiler, mocker):
    """空源文件返回成功但不创建页面"""
    empty_path = os.path.join(compiler.reader.base_dir, "sources", "empty.md")
    with open(empty_path, "w", encoding="utf-8") as f:
        f.write("")

    result = compiler.ingest("empty.md")
    assert result["status"] == "success"
    assert result["pages_created"] == []


def test_ingest_source_not_found(compiler):
    """源文件不存在抛出 CompilerError"""
    with pytest.raises(CompilerError, match="Source file not found"):
        compiler.ingest("nonexistent.md")


def test_ingest_llm_error(compiler, mocker):
    """LLM 调用失败时传播 LLMError"""
    mocker.patch.object(
        compiler.llm, "chat", side_effect=LLMError("API call failed")
    )

    with pytest.raises(LLMError, match="API call failed"):
        compiler.ingest("test.md")


def test_ingest_llm_returns_no_pages(compiler, mocker):
    """LLM 返回无法解析的内容时，返回成功但无页面"""
    mocker.patch.object(compiler.llm, "chat", return_value="没有发现任何实体或概念。")

    result = compiler.ingest("test.md")
    assert result["status"] == "success"
    assert result["pages_created"] == []


# ---------------------------------------------------------------------------
# 解析逻辑 — 单元测试
# ---------------------------------------------------------------------------


def test_parse_response_extracts_pages():
    """_parse_response 正确分割多个页面"""
    response = (
        "---PAGE:entities/a.md---\n# A\nContent A\n---END---\n"
        "---PAGE:concepts/b.md---\n# B\nContent B\n---END---"
    )
    pages = WikiCompiler._parse_response(response)
    assert len(pages) == 2
    assert "entities/a.md" in pages
    assert "concepts/b.md" in pages
    assert pages["entities/a.md"] == "# A\nContent A"


def test_parse_response_empty():
    """无有效分隔符时返回空字典"""
    pages = WikiCompiler._parse_response("随便一段文字，没有格式化输出。")
    assert pages == {}


def test_extract_links():
    """_extract_links 正确提取 [[...]] 链接"""
    content = "参见 [[entities/py.md|Python]] 和 [[concepts/ai.md]]"
    links = WikiCompiler._extract_links(content)
    assert "entities/py.md" in links
    assert "concepts/ai.md" in links
    assert len(links) == 2


def test_extract_title():
    """_extract_title 提取第一行 # 标题"""
    assert WikiCompiler._extract_title("# 你好\n正文") == "你好"
    assert WikiCompiler._extract_title("无标题内容") == "Untitled"


def test_guess_type(compiler):
    """_guess_type 根据路径推测类型"""
    assert compiler._guess_type("entities/python.md") == "entity"
    assert compiler._guess_type("concepts/ai.md") == "concept"
    assert compiler._guess_type("sources/intro.md") == "source"
