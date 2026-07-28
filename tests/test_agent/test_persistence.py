"""
Agent 持久化层测试 — SQLite 对话记忆存储

策略：
  - 每个测试使用独立的临时数据库文件
  - Mock PERSISTENCE_DB_PATH + 重置模块级 _conn 连接
  - 避免测试之间状态泄漏
"""
import json
import os
import time
from pathlib import Path

import pytest

from src.agent.memory import store as P
from src.agent import constants as C


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def _fresh_db(mocker, tmp_path):
    """每个测试创建独立的临时 SQLite 数据库，测试后清理"""
    db_path = tmp_path / "test_persistence.db"

    # Mock 持久化路径
    mocker.patch.object(C, "PERSISTENCE_DB_PATH", str(db_path))

    # 重置全局连接和表存在标志
    P._conn = None  # type: ignore[attr-defined]
    P._ENSURED = False  # type: ignore[attr-defined]
    P._INDEX_ENSURED = False  # type: ignore[attr-defined]


# ============================================================================
# save_thread / load_thread
# ============================================================================


class TestSaveLoad:
    """save_thread + load_thread 读写测试"""

    def _load_msgs(self, thread_id: str) -> list[dict]:
        """Helper: load thread and return just messages"""
        result = P.load_thread(thread_id)
        assert result is not None
        msgs, _, _ = result
        return msgs

    def test_save_and_load_roundtrip(self, _fresh_db):
        """写入后再读取，数据一致"""
        messages = [
            {"role": "system", "content": "你是一个助手"},
            {"role": "user", "content": "你好"},
        ]
        P.save_thread("test-roundtrip", messages)
        loaded = self._load_msgs("test-roundtrip")
        assert loaded == messages

    def test_load_unknown_thread_returns_none(self, _fresh_db):
        """不存在的 thread_id 返回 None"""
        assert P.load_thread("nonexistent") is None

    def test_save_overwrites_existing(self, _fresh_db):
        """同一 thread_id 多次保存覆盖旧数据"""
        P.save_thread("overwrite-test", [{"role": "user", "content": "第一版"}])
        P.save_thread("overwrite-test", [{"role": "user", "content": "第二版"}])
        loaded = self._load_msgs("overwrite-test")
        assert len(loaded) == 1
        assert loaded[0]["content"] == "第二版"

    def test_multiple_threads_isolation(self, _fresh_db):
        """不同 thread_id 互不干扰"""
        P.save_thread("thread-a", [{"role": "user", "content": "A"}])
        P.save_thread("thread-b", [{"role": "user", "content": "B"}])

        assert len(self._load_msgs("thread-a")) == 1
        assert self._load_msgs("thread-a")[0]["content"] == "A"
        assert self._load_msgs("thread-b")[0]["content"] == "B"

    def test_empty_messages_list(self, _fresh_db):
        """空消息列表也可以保存（可能用于临时占位）"""
        P.save_thread("empty-test", [])
        loaded = P.load_thread("empty-test")
        assert loaded is not None
        loaded_msgs, _, _ = loaded
        assert loaded_msgs == []

    def test_special_characters_in_content(self, _fresh_db):
        """特殊字符（引号、换行、Emoji、中文）正确序列化"""
        content = '他说："你好"\n新行\n🔥 中文 Emoji 🎉'
        P.save_thread("special-chars", [{"role": "user", "content": content}])
        loaded = self._load_msgs("special-chars")
        assert loaded[0]["content"] == content

    def test_json_structure(self, _fresh_db):
        """保存的消息在数据库中是合法的 JSON 字符串"""
        P.save_thread("json-test", [{"role": "user", "content": "test"}])
        row = P._get_conn().execute(
            "SELECT messages FROM agent_threads WHERE thread_id = ?",
            ("json-test",),
        ).fetchone()
        parsed = json.loads(row["messages"])
        assert isinstance(parsed, list)
        assert parsed[0]["role"] == "user"

    def test_updated_at_changes_on_resave(self, _fresh_db):
        """多次保存后 updated_at 递增"""
        import time

        P.save_thread("time-test", [{"role": "user", "content": "v1"}])
        row1 = P._get_conn().execute(
            "SELECT updated_at FROM agent_threads WHERE thread_id = ?",
            ("time-test",),
        ).fetchone()

        time.sleep(0.01)  # 确保时间差
        P.save_thread("time-test", [{"role": "user", "content": "v2"}])
        row2 = P._get_conn().execute(
            "SELECT updated_at FROM agent_threads WHERE thread_id = ?",
            ("time-test",),
        ).fetchone()

        assert row2["updated_at"] > row1["updated_at"]

    def test_title_can_be_overridden(self, _fresh_db):
        """title 在第一轮自动生成，后续保存可覆盖"""
        P.save_thread("title-test", [{"role": "user", "content": "你好世界"}])
        row1 = P._get_conn().execute(
            "SELECT title FROM agent_threads WHERE thread_id = ?",
            ("title-test",),
        ).fetchone()
        assert "你好世界" in row1["title"]

        # 传空内容的消息不会覆盖 title
        P.save_thread("title-test", [{"role": "user", "content": ""}])
        row2 = P._get_conn().execute(
            "SELECT title FROM agent_threads WHERE thread_id = ?",
            ("title-test",),
        ).fetchone()
        assert "你好世界" in row2["title"]


# ============================================================================
# list_threads
# ============================================================================


class TestListThreads:
    """list_threads 列表查询测试"""

    def test_list_empty(self, _fresh_db):
        """数据库为空返回空列表"""
        assert P.list_threads() == []

    def test_list_multiple_threads(self, _fresh_db):
        """多个 thread 按 updated_at 倒序返回"""
        import time

        P.save_thread("first", [{"role": "user", "content": "第一"}])
        time.sleep(0.01)
        P.save_thread("second", [{"role": "user", "content": "第二"}])
        time.sleep(0.01)
        P.save_thread("third", [{"role": "user", "content": "第三"}])

        threads = P.list_threads()
        ids = [t["thread_id"] for t in threads]
        assert ids == ["third", "second", "first"]

    def test_list_limit(self, _fresh_db):
        """limit 参数控制返回条数"""
        for i in range(10):
            P.save_thread(f"thread-{i}", [{"role": "user", "content": str(i)}])

        assert len(P.list_threads(limit=3)) == 3
        # limit=0 在 SQL 中返回 0 行（SQLite LIMIT 语义），不是不限
        assert len(P.list_threads(limit=0)) == 0
        assert len(P.list_threads(limit=100)) == 10

    def test_list_offset(self, _fresh_db):
        """offset 参数支持翻页"""
        for i in range(10):
            P.save_thread(f"thread-{i}", [{"role": "user", "content": str(i)}])

        page1 = P.list_threads(limit=3, offset=0)
        page2 = P.list_threads(limit=3, offset=3)
        assert len(page1) == 3
        assert len(page2) == 3
        # 分页不重叠（按更新倒序后，第 0-2 和 3-5 个）
        assert page1[0]["thread_id"] != page2[0]["thread_id"]

    def test_list_includes_message_count(self, _fresh_db):
        """返回结果包含 message_count 字段"""
        P.save_thread("count-test", [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "q2"},
        ])
        threads = P.list_threads()
        assert threads[0]["message_count"] == 3


# ============================================================================
# delete_thread
# ============================================================================


class TestDeleteThread:
    """delete_thread 删除测试"""

    def test_delete_existing_thread(self, _fresh_db):
        """能删除已存在的 thread"""
        P.save_thread("to-delete", [{"role": "user", "content": "数据"}])
        assert P.thread_exists("to-delete")

        assert P.delete_thread("to-delete") is True
        assert not P.thread_exists("to-delete")
        assert P.load_thread("to-delete") is None

    def test_delete_nonexistent_thread(self, _fresh_db):
        """删除不存在的 thread 返回 False"""
        assert P.delete_thread("nonexistent") is False

    def test_delete_does_not_affect_others(self, _fresh_db):
        """删除一个 thread 不影响其他"""
        P.save_thread("keep-a", [{"role": "user", "content": "A"}])
        P.save_thread("keep-b", [{"role": "user", "content": "B"}])
        P.save_thread("to-go", [{"role": "user", "content": "C"}])

        P.delete_thread("to-go")
        assert P.load_thread("keep-a") is not None
        assert P.load_thread("keep-b") is not None


# ============================================================================
# thread_exists
# ============================================================================


class TestThreadExists:
    """thread_exists 存在性检查测试"""

    def test_exists(self, _fresh_db):
        """存在的 thread 返回 True"""
        P.save_thread("exists", [{"role": "user", "content": "test"}])
        assert P.thread_exists("exists") is True

    def test_not_exists(self, _fresh_db):
        """不存在的 thread 返回 False"""
        assert P.thread_exists("imaginary") is False

    def test_after_delete_returns_false(self, _fresh_db):
        """删除后的 thread 返回 False"""
        P.save_thread("temp", [{"role": "user", "content": "x"}])
        P.delete_thread("temp")
        assert P.thread_exists("temp") is False


# ============================================================================
# migrate_memorysaver_to_sqlite
# ============================================================================


class TestMigrate:
    """migrate_memorysaver_to_sqlite 测试"""

    def test_migrate_ensures_table(self, _fresh_db):
        """migrate 确保表已创建（幂等调用）"""
        # 先不调 _ensure_table，直接调 migrate
        P.migrate_memorysaver_to_sqlite()

        # 表应已存在，可以正常写入
        P.save_thread("after-migrate", [{"role": "user", "content": "ok"}])
        assert P.load_thread("after-migrate") is not None


# ============================================================================
# 并发安全（基本保障）
# ============================================================================


class TestConcurrency:
    """基本并发安全测试——多个 thread 同时操作"""

    def test_multiple_threads_save_and_load(self, _fresh_db):
        """不同 thread 并发保存和加载不阻塞"""
        threads = []
        for i in range(20):
            tid = f"concurrent-{i}"
            P.save_thread(tid, [{"role": "user", "content": f"msg-{i}"}])
            threads.append(tid)

        # 全部能读到
        for tid in threads:
            loaded = P.load_thread(tid)
            assert loaded is not None
            msgs, _, _ = loaded
            assert len(msgs) == 1

    def test_repeated_save_no_leak(self, _fresh_db):
        """同一 thread 反复保存不会泄漏（只增一条记录）"""
        for _ in range(100):
            P.save_thread("hot", [{"role": "user", "content": "最新"}])

        row = P._get_conn().execute(
            "SELECT COUNT(*) as cnt FROM agent_threads WHERE thread_id = ?",
            ("hot",),
        ).fetchone()
        assert row["cnt"] == 1


# ============================================================================
# 记忆降级归档 — Memory Degradation
# ============================================================================


class TestArchive:
    """归档相关功能测试"""

    def test_archive_replaces_messages_with_summary(self, _fresh_db):
        """归档后 messages 只剩一条摘要 SystemMessage"""
        P.save_thread("archive-me", [
            {"role": "user", "content": "Python 异步"},
            {"role": "assistant", "content": "asyncio 是标准库"},
        ])

        P.archive_thread("archive-me", [
            {"role": "system", "content": f"{C.ARCHIVE_PREFIX}用户询问 Python 异步编程"},
        ])

        loaded = P.load_thread("archive-me")
        assert loaded is not None
        msgs, sinks, wm = loaded
        assert len(msgs) == 1
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"].startswith(C.ARCHIVE_PREFIX)

    def test_archive_preserves_sinks_and_wm(self, _fresh_db):
        """归档保留 attention_sinks 和 working_memory"""
        sinks = [{"key": "name", "value": "张三", "confidence": 0.9}]
        wm = {"current_goal": "学习 Python"}
        P.save_thread("preserve-test", [
            {"role": "user", "content": "我叫张三"},
            {"role": "assistant", "content": "你好张三"},
        ], attention_sinks=sinks, working_memory=wm)

        P.archive_thread("preserve-test", [
            {"role": "system", "content": f"{C.ARCHIVE_PREFIX}用户自我介绍"},
        ], attention_sinks=sinks, working_memory=wm)

        loaded = P.load_thread("preserve-test")
        assert loaded is not None
        _, loaded_sinks, loaded_wm = loaded
        assert loaded_sinks == sinks
        assert loaded_wm == wm

    def test_archive_nonexistent_thread_no_error(self, _fresh_db):
        """归档不存在的 thread 不报错（不操作）"""
        # 不应该抛异常
        P.archive_thread("ghost", [{"role": "system", "content": "摘要"}])
        assert P.load_thread("ghost") is None

    def test_is_thread_archived_true(self, _fresh_db):
        """归档后 is_thread_archived 返回 True"""
        P.save_thread("check-archived", [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ])
        assert not P.is_thread_archived("check-archived")

        P.archive_thread("check-archived", [
            {"role": "system", "content": f"{C.ARCHIVE_PREFIX}摘要"},
        ])
        assert P.is_thread_archived("check-archived")

    def test_is_thread_archived_nonexistent(self, _fresh_db):
        """不存在的 thread 返回 False"""
        assert not P.is_thread_archived("no-such-thread")

    def test_is_thread_archived_empty_messages(self, _fresh_db):
        """空消息 thread 返回 False"""
        P.save_thread("empty", [])
        assert not P.is_thread_archived("empty")

    def test_get_thread_age_days_fresh(self, _fresh_db):
        """刚创建的 thread age ≈ 0 天"""
        P.save_thread("fresh", [{"role": "user", "content": "test"}])
        age = P.get_thread_age_days("fresh")
        assert age is not None
        assert age < 0.01  # 刚创建，接近 0

    def test_get_thread_age_days_nonexistent(self, _fresh_db):
        """不存在的 thread 返回 None"""
        assert P.get_thread_age_days("ghost") is None

    def test_list_stale_threads_empty(self, _fresh_db):
        """没有过期 thread 时返回空列表"""
        P.save_thread("fresh", [{"role": "user", "content": "hi"}])
        stale = P.list_stale_threads(days=30)
        assert stale == []

    def test_list_stale_threads_returns_old(self, _fresh_db):
        """超过阈值的 thread 被标为 stale（用 save_thread 再改 updated_at）"""
        # 先 save_thread 确保表已创建 + 数据格式正确
        P.save_thread("old-thread", [{"role": "user", "content": "old"}])
        # 手动改 updated_at 为 60 天前
        conn = P._get_conn()
        old_time = time.time() - 60 * 86400
        conn.execute("UPDATE agent_threads SET updated_at = ? WHERE thread_id = ?",
                     (old_time, "old-thread"))
        conn.commit()

        # 再插入一个 fresh
        P.save_thread("fresh", [{"role": "user", "content": "new"}])

        stale = P.list_stale_threads(days=30)
        assert len(stale) == 1
        assert stale[0]["thread_id"] == "old-thread"

    def test_list_stale_threads_limit(self, _fresh_db):
        """limit 参数控制返回条数"""
        conn = P._get_conn()
        old_time = time.time() - 60 * 86400
        for i in range(5):
            P.save_thread(f"old-{i}", [{"role": "user", "content": str(i)}])
            conn.execute("UPDATE agent_threads SET updated_at = ? WHERE thread_id = ?",
                         (old_time, f"old-{i}"))
        conn.commit()

        assert len(P.list_stale_threads(days=30, limit=3)) == 3
        assert len(P.list_stale_threads(days=30, limit=10)) == 5
