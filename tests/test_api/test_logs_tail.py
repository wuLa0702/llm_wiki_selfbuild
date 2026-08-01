"""
日志查看接口测试 — GET /v1/logs/tail

验证：能读取后端日志（logs/wiki.log）和前端日志（.logs/frontend.log）的尾部。
"""
import json

import pytest

from src.api.routes import misc as misc_mod
from src.core.logging_config import LOGGER_NAME, reset_logging


@pytest.fixture(autouse=True)
def reset_logging_after():
    yield
    reset_logging()


@pytest.fixture
def patched_log_dir(monkeypatch, tmp_path):
    """把日志目录指向 tmp_path 并写入测试日志"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "wiki.log").write_text(
        "2026-08-01 10:00:00 [INFO] line1\n"
        "2026-08-01 10:00:01 [INFO] line2\n"
        "2026-08-01 10:00:02 [ERROR] boom\n",
        encoding="utf-8",
    )
    front_dir = tmp_path / ".logs"
    front_dir.mkdir()
    (front_dir / "frontend.log").write_text(
        '{"ts":"2026-08-01 10:00:00","level":"error","source":"SourcesPage","message":"upload failed"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(misc_mod, "get_log_dir", lambda: str(log_dir), raising=False)
    return str(log_dir)


class TestLogsTail:
    def test_backend_tail_returns_lines(self, client, patched_log_dir):
        """默认返回后端日志尾部"""
        resp = client.get("/v1/logs/tail")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "backend"
        assert "line2" in data["content"]
        assert "boom" in data["content"]

    def test_tail_lines_limit(self, client, patched_log_dir):
        """lines 参数限制返回行数"""
        resp = client.get("/v1/logs/tail?lines=2")
        data = resp.json()
        lines = [l for l in data["content"].splitlines() if l.strip()]
        assert len(lines) <= 2

    def test_frontend_tail(self, client, patched_log_dir):
        """source=frontend 返回前端日志"""
        resp = client.get("/v1/logs/tail?source=frontend")
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "frontend"
        assert "upload failed" in data["content"]

    def test_missing_log_file(self, client, monkeypatch, tmp_path):
        """日志文件不存在时返回空内容而非 500"""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        monkeypatch.setattr(misc_mod, "get_log_dir", lambda: str(empty_dir), raising=False)
        resp = client.get("/v1/logs/tail")
        assert resp.status_code == 200
        assert resp.json()["content"] == ""
