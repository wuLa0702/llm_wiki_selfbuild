"""
上传 → 提取到 Wiki 端到端模拟 — 单个/多个简单文件

回归 2026-08-01：上传后提取失败（LLM 偶发输出 wiki/ 前缀路径
→ ValidatorError 拒绝 → 队列任务 failed）。

本测试走真实链路：POST /v1/ingest/upload（文件落盘）
→ import_folder_async 入队 → IngestQueue worker 消费 → WikiCompiler.ingest
→ wiki/ 页面生成。LLM 全 mock，数据目录隔离到 tmp_path。
"""
import os
import time

import pytest

from src.utils import path_resolver


@pytest.fixture
def e2e_client():
    """显式触发 lifespan（init_services 启动队列 worker）的 TestClient"""
    from fastapi.testclient import TestClient
    from src.main import app

    with TestClient(app) as client:
        yield client


# path_resolver 函数被 22 个模块在 import 时绑定（from X import Y 绑定旧对象），
# 仅 patch path_resolver 模块本身对它们无效 → 必须逐一 patch 使用方模块，
# 否则 importer/queue/cache 指向真实 CWD 目录导致测试间串扰。
_PATH_RESOLVER_CONSUMERS = [
    "src.api.routes.ingest",
    "src.api.routes.misc",
    "src.api.routes.purpose",
    "src.api.routes.sources",
    "src.api.routes.system",
    "src.core.cache",
    "src.core.embedding",
    "src.core.graph.graph",
    "src.core.ingest.importer",
    "src.core.ingest.ingest_queue",
    "src.core.logging_config",
    "src.core.pricing",
    "src.core.privacy",
    "src.core.task_queue",
    "src.core.token_tracker",
    "src.core.watcher",
    "src.db.repository",
    "src.main",
    "src.tools.path_utils",
    "src.tools.search_tool",
    "src.utils.config_manager",
    "src.agent.memory.store",
]

_PATH_FUNCS = (
    "get_raw_sources_dir", "get_raw_dir", "get_wiki_dir",
    "get_app_dir", "get_log_dir", "get_db_path",
)


@pytest.fixture
def isolated_env(monkeypatch, tmp_path):
    """数据目录全部隔离到 tmp_path + LLM mock"""
    raw = tmp_path / "raw"
    sources = raw / "sources"
    sources.mkdir(parents=True)
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    paths = {
        "get_raw_sources_dir": lambda: str(sources),
        "get_raw_dir": lambda: str(raw),
        "get_wiki_dir": lambda: str(wiki),
        "get_app_dir": lambda: str(app_dir),
        "get_log_dir": lambda: str(app_dir / "logs"),
        "get_db_path": lambda name: str(app_dir / name),
    }
    for mod_name in _PATH_RESOLVER_CONSUMERS:
        mod = __import__(mod_name, fromlist=["*"])
        for func in _PATH_FUNCS:
            if hasattr(mod, func):
                monkeypatch.setattr(mod, func, paths[func])
    monkeypatch.setattr(path_resolver, "get_raw_sources_dir", paths["get_raw_sources_dir"])
    monkeypatch.setattr(path_resolver, "get_raw_dir", paths["get_raw_dir"])
    monkeypatch.setattr(path_resolver, "get_wiki_dir", paths["get_wiki_dir"])
    monkeypatch.setattr(path_resolver, "get_app_dir", paths["get_app_dir"])
    monkeypatch.setattr(path_resolver, "get_log_dir", paths["get_log_dir"])
    monkeypatch.setattr(path_resolver, "get_db_path", paths["get_db_path"])

    from src.llm.adapter import LLMAdapter

    def fake_structured(self, **kwargs):
        return {
            "entities": [{"name": "Python", "type": "tool", "importance": "high"}],
            "concepts": [{"name": "人工智能", "type": "concept", "importance": "high"}],
            "contradictions": [],
            "connections_to_existing": [],
            "recommendations": [],
        }

    def fake_template(self, *args, **kwargs):
        return """---PAGE:entities/python.md---
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

    monkeypatch.setattr(LLMAdapter, "chat_structured", fake_structured)
    monkeypatch.setattr(LLMAdapter, "chat_template", fake_template)

    # _update_overview 也走 chat → mock 掉
    monkeypatch.setattr(LLMAdapter, "chat", lambda self, **kwargs: "# Overview 综述\n- [[entities/python.md]]")

    return {"sources": str(sources), "wiki": str(wiki)}


def _wait_queue_done(client, timeout: float = 30.0) -> dict:
    """轮询队列状态直到全部任务终态（done/failed/cancelled）"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        resp = client.get("/v1/ingest/queue/status")
        stats = resp.json()
        if stats.get("pending", 0) == 0 and stats.get("processing", 0) == 0:
            return stats
        time.sleep(0.5)
    raise AssertionError(f"队列任务未在 {timeout}s 内消费完: {stats}")


class TestUploadIngestE2E:
    """上传 → 提取到 wiki 全链路模拟"""

    def test_upload_single_simple_file_extracts_to_wiki(self, isolated_env, e2e_client):
        """单个简单 .md 文件：上传 → 队列消费 → wiki 页面生成"""
        payload = {"f0": ("hello.md", "# Hello\n\n简单内容 [[concepts/ai.md]]".encode("utf-8"), "text/markdown")}
        resp = e2e_client.post("/v1/ingest/upload", files=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] == 1, f"上传未落盘: {data}"
        assert data["enqueued"] >= 1, f"未入队: {data}"

        stats = _wait_queue_done(e2e_client)
        assert stats["failed"] == 0, f"队列任务失败: {stats}"
        assert stats["done"] >= 1, f"无完成任务: {stats}"

        # wiki 页面真实生成
        assert os.path.exists(os.path.join(isolated_env["wiki"], "entities", "python.md"))
        assert os.path.exists(os.path.join(isolated_env["wiki"], "concepts", "ai.md"))

    def test_upload_multiple_simple_files_all_extract(self, isolated_env, e2e_client):
        """多个简单 .md 文件：全部上传、全部消费、全部提取"""
        payload = {}
        for i in range(3):
            payload[f"f{i}"] = (f"file_{i}.md", f"# 文件 {i}\n\n内容 {i} [[concepts/ai.md]]".encode("utf-8"), "text/markdown")
        resp = e2e_client.post("/v1/ingest/upload", files=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] == 3, f"上传丢失: {data}"
        assert data["enqueued"] >= 3, f"入队不足: {data}"

        stats = _wait_queue_done(e2e_client)
        assert stats["failed"] == 0, f"队列任务失败: {stats}"
        assert stats["done"] >= 3, f"完成任务不足: {stats}"

        assert os.path.exists(os.path.join(isolated_env["wiki"], "entities", "python.md"))

    def test_upload_with_wiki_prefix_llm_output_still_succeeds(self, isolated_env, e2e_client):
        """LLM 输出 wiki/ 前缀路径（真实故障场景）→ 归一化后仍成功"""
        from src.llm.adapter import LLMAdapter

        original_template = LLMAdapter.chat_template
        original_chat = LLMAdapter.chat

        def wiki_prefix_template(self, *args, **kwargs):
            return """---PAGE:wiki/entities/python.md---
---
title: "Python"
type: entity
tags: [编程语言]
---
# Python

Python 用于 [[concepts/ai.md|人工智能]]。
---END---
---PAGE:wiki/index.md---
---
title: "Python 索引"
type: overview
---
# 索引

Python 常用 [[entities/python.md|Python]]。
---END---"""

        LLMAdapter.chat_template = wiki_prefix_template
        try:
            payload = {"f0": ("hello.md", "# Hello\n\n简单内容".encode("utf-8"), "text/markdown")}
            resp = e2e_client.post("/v1/ingest/upload", files=payload)
            assert resp.status_code == 200
            assert resp.json()["saved"] == 1

            stats = _wait_queue_done(e2e_client)
            assert stats["failed"] == 0, f"wiki/ 前缀路径仍致任务失败: {stats}"
            assert os.path.exists(os.path.join(isolated_env["wiki"], "entities", "python.md"))
            assert os.path.exists(os.path.join(isolated_env["wiki"], "index.md"))
        finally:
            LLMAdapter.chat_template = original_template
            LLMAdapter.chat = original_chat
