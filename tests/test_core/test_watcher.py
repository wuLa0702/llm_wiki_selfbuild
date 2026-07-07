"""
SourceWatcher 单元测试 — Phase 3 Step 8
"""
import os
import time

import pytest

from src.core.watcher import SourceWatcher


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sources_dir(tmp_path):
    d = tmp_path / "raw" / "sources"
    d.mkdir(parents=True)
    return str(d)


@pytest.fixture
def watcher(sources_dir):
    return SourceWatcher(sources_dir=sources_dir, poll_interval=3600)


# ============================================================================
# 启动 / 停止
# ============================================================================


class TestLifecycle:
    """启动/停止生命周期"""

    def test_start_sets_running(self, watcher):
        """start() 后 is_running 为 True"""
        watcher.start()
        assert watcher.is_running
        watcher.stop()

    def test_stop_clears_running(self, watcher):
        """stop() 后 is_running 为 False"""
        watcher.start()
        watcher.stop()
        assert not watcher.is_running

    def test_start_idempotent(self, watcher):
        """重复 start() 不报错"""
        watcher.start()
        watcher.start()  # 第二次调用不应异常
        assert watcher.is_running
        watcher.stop()

    def test_stop_idempotent(self, watcher):
        """重复 stop() 不报错"""
        watcher.stop()
        watcher.stop()  # 未启动时调用不应异常

    def test_start_creates_dir(self, tmp_path):
        """启动时目录不存在则自动创建"""
        non_existent = str(tmp_path / "auto" / "sources")
        w = SourceWatcher(sources_dir=non_existent, poll_interval=3600)
        w.start()
        assert os.path.isdir(non_existent)
        w.stop()


# ============================================================================
# 状态查询
# ============================================================================


class TestStatus:
    """状态查询"""

    def test_status_stopped(self, watcher):
        """未启动时返回正确状态"""
        s = watcher.status()
        assert s["running"] is False
        assert s["watched_dir"] == watcher.sources_dir
        assert s["poll_interval_seconds"] == watcher.poll_interval

    def test_status_running(self, watcher):
        """启动后状态包含运行信息"""
        watcher.start()
        s = watcher.status()
        assert s["running"] is True
        assert s["files_processed"] == 0
        assert s["last_check"] == ""  # 还没执行扫描
        watcher.stop()

    def test_status_tracks_processed(self, watcher, mocker):
        """处理后 files_processed 更新"""
        mocker.patch.object(watcher, "_scan_and_ingest")
        watcher.start()
        # 模拟一次扫描处理
        watcher._files_processed = 5
        s = watcher.status()
        assert s["files_processed"] == 5
        watcher.stop()


# ============================================================================
# 扫描与 ingest
# ============================================================================


class TestScanAndIngest:
    """扫描与自动 ingest"""

    def test_scans_md_only(self, watcher, sources_dir, mocker):
        """只扫描 .md 文件，跳过其他"""
        from pathlib import Path
        sd = Path(sources_dir)
        (sd / "test.md").write_text("hello", encoding="utf-8")
        (sd / "notes.txt").write_text("hello", encoding="utf-8")
        (sd / ".gitkeep").write_text("", encoding="utf-8")
        (sd / "image.png").write_bytes(b"\x89PNG\r\n")

        called_with = []
        mock_compiler = mocker.patch("src.core.watcher.WikiCompiler")
        mock_instance = mock_compiler.return_value
        mock_instance.ingest.return_value = {
            "status": "success", "pages_created": [], "pages_updated": [],
        }

        watcher._scan_and_ingest()
        assert "test.md" in called_with or mock_instance.ingest.call_count >= 1
        # 验证只被调用了 1 次（只有 test.md）
        assert mock_instance.ingest.call_count == 1

    def test_skip_hidden_files(self, watcher, sources_dir, mocker):
        """跳过以 . 开头的隐藏文件"""
        from pathlib import Path
        sd = Path(sources_dir)
        (sd / ".hidden.md").write_text("secret", encoding="utf-8")
        (sd / "visible.md").write_text("hello", encoding="utf-8")

        mock_compiler = mocker.patch("src.core.watcher.WikiCompiler")
        mock_instance = mock_compiler.return_value
        mock_instance.ingest.return_value = {
            "status": "success", "pages_created": [], "pages_updated": [],
        }

        watcher._scan_and_ingest()
        # 验证 ingest 被调用，且参数是 visible.md 而非 .hidden.md
        called_path = mock_instance.ingest.call_args[0][0]
        assert called_path == "visible.md"

    def test_cache_hit_skipped(self, watcher, sources_dir, mocker):
        """已缓存的文件返回 skipped 状态，不计数"""
        from pathlib import Path
        (Path(sources_dir) / "cached.md").write_text("old", encoding="utf-8")

        mock_compiler = mocker.patch("src.core.watcher.WikiCompiler")
        mock_instance = mock_compiler.return_value
        mock_instance.ingest.return_value = {
            "status": "skipped", "message": "Cached",
        }

        watcher._scan_and_ingest()
        assert watcher._files_processed == 0  # skipped 不计
        assert mock_instance.ingest.call_count == 1

    def test_no_files_no_error(self, watcher, sources_dir):
        """空目录不报错"""
        watcher._scan_and_ingest()  # 不应抛出异常
        assert watcher._files_processed == 0

    def test_source_dir_not_exist(self, watcher):
        """源目录不存在时不报错"""
        watcher.sources_dir = "/nonexistent/path"
        watcher._scan_and_ingest()  # 不应抛出异常


# ============================================================================
# API 路由
# ============================================================================


class TestWatcherAPI:
    """POST/GET /v1/watcher/* 端点测试"""

    def test_watcher_status_not_running(self, client):
        """未启动时返回 running=false"""
        response = client.get("/v1/watcher/status")
        assert response.status_code == 200
        data = response.json()
        assert data["running"] is False

    def test_watcher_start(self, client):
        """POST /v1/watcher/start 返回 started"""
        response = client.post("/v1/watcher/start")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "started" or data["status"] == "already_running"

    def test_watcher_stop(self, client):
        """POST /v1/watcher/stop 返回 stopped"""
        response = client.post("/v1/watcher/stop")
        assert response.status_code == 200
        assert response.json()["status"] in ("stopped", "not_running")

    def test_watcher_start_then_status_running(self, client):
        """启动后状态为 running"""
        client.post("/v1/watcher/start")
        response = client.get("/v1/watcher/status")
        assert response.json()["running"] is True

    def test_watcher_stop_then_status_not_running(self, client):
        """停止后状态为 not running"""
        client.post("/v1/watcher/start")
        client.post("/v1/watcher/stop")
        response = client.get("/v1/watcher/status")
        assert response.json()["running"] is False
