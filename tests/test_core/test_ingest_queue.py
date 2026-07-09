"""
IngestQueue 单元测试 — Phase 4 Step 7
"""
import os

import pytest

from src.core.ingest import IngestQueue


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def q(tmp_path):
    """使用临时数据库的 IngestQueue 实例"""
    db = str(tmp_path / "test_queue.db")
    return IngestQueue(db_path=db, poll_interval=0.1)


# ============================================================================
# 队列操作
# ============================================================================


def test_enqueue_returns_job_id(q):
    """enqueue 返回有效的 job_id"""
    job_id = q.enqueue("test.md")
    assert len(job_id) == 12
    assert isinstance(job_id, str)


def test_enqueue_with_context(q):
    """enqueue 支持传入上下文"""
    job_id = q.enqueue("test.md", context={"folder": "papers"})
    status = q.status(job_id)
    assert status is not None
    import json
    ctx = json.loads(status["context"])
    assert ctx["folder"] == "papers"


def test_status_returns_full_info(q):
    """status 返回任务完整信息"""
    job_id = q.enqueue("test.md")
    s = q.status(job_id)
    assert s["job_id"] == job_id
    assert s["source_path"] == "test.md"
    assert s["status"] == "pending"


def test_status_nonexistent(q):
    """不存在的 job_id 返回 None"""
    assert q.status("nonexistent") is None


# ============================================================================
# 取消
# ============================================================================


def test_cancel_pending(q):
    """取消 pending 状态的任务"""
    job_id = q.enqueue("test.md")
    assert q.cancel(job_id) is True
    assert q.status(job_id)["status"] == "cancelled"


def test_cancel_nonexistent(q):
    """取消不存在的任务返回 False"""
    assert q.cancel("nonexistent") is False


# ============================================================================
# 重试
# ============================================================================


def test_retry_fails_if_not_failed(q):
    """非 failed 状态的任务 retry 返回 False"""
    job_id = q.enqueue("test.md")
    assert q.retry(job_id) is False


def test_retry_failed(q):
    """failed 状态的任务 retry 后恢复为 pending"""
    job_id = q.enqueue("test.md")
    # 手动设为 failed
    import sqlite3
    conn = sqlite3.connect(q.db_path)
    conn.execute("UPDATE ingest_queue SET status='failed', error='test error' WHERE job_id=?", (job_id,))
    conn.commit()
    conn.close()

    assert q.retry(job_id) is True
    assert q.status(job_id)["status"] == "pending"
    assert q.status(job_id)["error"] == ""


# ============================================================================
# 进度统计
# ============================================================================


def test_progress_empty(q):
    """空队列返回全 0"""
    p = q.progress()
    assert p["total"] == 0
    assert p["pending"] == 0


def test_progress_counts(q):
    """progress 正确统计各状态数量"""
    q.enqueue("a.md")
    q.enqueue("b.md")
    j3 = q.enqueue("c.md")
    q.cancel(j3)

    p = q.progress()
    assert p["total"] == 3
    assert p["pending"] == 2
    assert p["cancelled"] == 1


# ============================================================================
# 崩溃恢复
# ============================================================================


def test_recover_processing(tmp_path):
    """启动时将 processing 状态重置为 pending"""
    db = str(tmp_path / "test.db")
    # 先创建表并写入 processing 任务
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS ingest_queue (job_id TEXT PRIMARY KEY, source_path TEXT, status TEXT, context TEXT DEFAULT '{}', result_summary TEXT DEFAULT '', error TEXT DEFAULT '', created_at TEXT, updated_at TEXT)"
    )
    conn.execute("INSERT INTO ingest_queue (job_id, source_path, status, created_at, updated_at) VALUES ('j1', 'a.md', 'processing', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO ingest_queue (job_id, source_path, status, created_at, updated_at) VALUES ('j2', 'b.md', 'pending', '2026-01-01', '2026-01-01')")
    conn.commit()
    conn.close()

    # 创建新实例（触发崩溃恢复）
    q = IngestQueue(db_path=db)
    assert q.status("j1")["status"] == "pending"  # recovered
    assert q.status("j2")["status"] == "pending"  # unchanged


# ============================================================================
# process_next
# ============================================================================


def test_process_next_no_jobs(q):
    """无待处理任务时返回 None"""
    assert q.process_next() is None


def test_process_next_processes_pending(q, mocker):
    """process_next 处理 pending 任务并调用 WikiCompiler"""
    # Mock WikiCompiler
    mock_compiler = mocker.patch("src.core.ingest.ingest_queue.WikiCompiler")
    mock_instance = mock_compiler.return_value
    mock_instance.ingest.return_value = {"status": "success", "pages_created": ["p1.md"], "pages_updated": []}

    q.enqueue("test.md")
    result = q.process_next()

    assert result is not None
    assert result["status"] == "done"
    mock_instance.ingest.assert_called_once_with("test.md")


def test_process_next_failure(q, mocker):
    """process_next 处理失败时标记为 failed"""
    mock_compiler = mocker.patch("src.core.ingest.ingest_queue.WikiCompiler")
    mock_instance = mock_compiler.return_value
    mock_instance.ingest.side_effect = RuntimeError("ingest failed")

    q.enqueue("test.md")
    result = q.process_next()

    assert result["status"] == "failed"
    assert "ingest failed" in result["error"]
    assert q.status(result["job_id"])["status"] == "failed"


# ============================================================================
# 后台线程
# ============================================================================


def test_start_stop(q):
    """start/stop 不抛异常"""
    q.start()
    assert q._running is True
    q.stop()
    assert q._running is False


def test_worker_processes_jobs(q, mocker):
    """worker 自动处理队列中的任务"""
    mock_compiler = mocker.patch("src.core.ingest.ingest_queue.WikiCompiler")
    mock_instance = mock_compiler.return_value
    mock_instance.ingest.return_value = {"status": "success", "pages_created": [], "pages_updated": []}

    q.enqueue("auto.md")
    q.start()
    import time
    time.sleep(0.3)
    q.stop()

    # 任务应该已被处理
    p = q.progress()
    assert p["done"] >= 1
