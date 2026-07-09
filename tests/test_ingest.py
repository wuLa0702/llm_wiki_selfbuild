"""
Ingest API 端点测试
"""
import pytest


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------


def test_ingest_endpoint_success(client, mocker):
    """有效请求返回 200 + IngestResponse（含 token_usage）"""
    mock_result = {
        "status": "success",
        "pages_created": ["entities/test.md"],
        "pages_updated": [],
        "message": "Ingested 'test.md': 1 created, 0 updated.",
        "token_usage": {
            "step1_input": 800,
            "step1_output": 200,
            "total": 1000,
        },
    }
    mocker.patch(
        "src.api.routes.ingest.WikiCompiler.ingest",
        return_value=mock_result,
    )

    response = client.post("/v1/ingest", json={"source_path": "test.md"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "entities/test.md" in data["pages_created"]
    assert data["token_usage"]["total"] == 1000


def test_ingest_endpoint_creates_and_updates(client, mocker):
    """返回同时包含 created 和 updated 的页面"""
    mock_result = {
        "status": "success",
        "pages_created": ["entities/new.md"],
        "pages_updated": ["entities/old.md"],
        "message": "Ingested: 1 created, 1 updated.",
    }
    mocker.patch("src.api.routes.ingest.WikiCompiler.ingest", return_value=mock_result)

    response = client.post("/v1/ingest", json={"source_path": "test.md"})
    assert response.status_code == 200
    data = response.json()
    assert len(data["pages_created"]) == 1
    assert len(data["pages_updated"]) == 1


def test_ingest_empty_source(client, mocker):
    """空源文件的 ingest 返回成功且无页面"""
    mock_result = {
        "status": "success",
        "pages_created": [],
        "pages_updated": [],
        "message": "Source file 'empty.md' is empty, nothing to ingest.",
    }
    mocker.patch("src.api.routes.ingest.WikiCompiler.ingest", return_value=mock_result)

    response = client.post("/v1/ingest", json={"source_path": "empty.md"})
    assert response.status_code == 200
    assert response.json()["pages_created"] == []


# ---------------------------------------------------------------------------
# 错误路径
# ---------------------------------------------------------------------------


def test_ingest_source_not_found(client, mocker):
    """源文件不存在返回 404"""
    from src.core.compiler import CompilerError

    mocker.patch(
        "src.api.routes.ingest.WikiCompiler.ingest",
        side_effect=CompilerError("Source file not found: raw/sources/nope.md"),
    )

    response = client.post("/v1/ingest", json={"source_path": "nope.md"})
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_ingest_llm_error(client, mocker):
    """LLM 调用失败返回 500"""
    from src.llm.adapter import LLMError

    mocker.patch(
        "src.api.routes.ingest.WikiCompiler.ingest",
        side_effect=LLMError("LLM call failed"),
    )

    response = client.post("/v1/ingest", json={"source_path": "test.md"})
    assert response.status_code == 500
    assert response.json()["code"] == "LLM_ERROR"


def test_ingest_missing_source_path(client):
    """缺少必填字段返回 422（Pydantic 校验）"""
    response = client.post("/v1/ingest", json={})
    assert response.status_code == 422
