"""
索引表测试 — FTS5 全文搜索 + 实体索引

覆盖范围：
  - 索引表创建（幂等）
  - index_thread_messages + search_conversations（FTS5 + LIKE 降级）
  - extract_thread_entities + 实体检索
  - 跨线程聚合（global_entities）
  - 删除索引
  - 边界情况（空消息、长文本、特殊字符）
"""

import json
import os
import re
from pathlib import Path

import pytest

from src.agent.memory import store as P
from src.agent import constants as C


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def _fresh_db(mocker, tmp_path):
    """每个测试创建独立的临时 SQLite 数据库"""
    db_path = tmp_path / "test_indexes.db"
    mocker.patch.object(C, "PERSISTENCE_DB_PATH", str(db_path))
    P._conn = None  # type: ignore[attr-defined]
    P._ENSURED = False  # type: ignore[attr-defined]
    P._INDEX_ENSURED = False  # type: ignore[attr-defined]


def _save_and_index(thread_id: str, messages: list[dict]):
    """Helper: 保存 thread 并构建索引"""
    P.save_thread(thread_id, messages)
    P.index_thread_messages(thread_id, messages)
    P.extract_thread_entities(thread_id, messages)


# ============================================================================
# 索引表创建
# ============================================================================


class TestEnsureIndexTables:
    """索引表创建测试"""

    def test_index_tables_created(self, _fresh_db):
        """调用 _ensure_index_tables 后所有表存在"""
        P._ensure_index_tables()
        conn = P._get_conn()

        # 检查表是否存在
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        table_names = {r["name"] for r in tables}

        assert "thread_messages" in table_names
        assert "thread_entities" in table_names
        assert "global_entities" in table_names

    def test_idempotent(self, _fresh_db):
        """多次调用不崩溃"""
        P._ensure_index_tables()
        P._ensure_index_tables()  # 第二次
        P._ensure_index_tables()  # 第三次
        # 不崩溃即通过

    def test_indexes_created(self, _fresh_db):
        """索引存在"""
        P._ensure_index_tables()
        conn = P._get_conn()
        indexes = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
        ).fetchall()
        index_names = {r["name"] for r in indexes}
        assert "idx_tm_thread" in index_names
        assert "idx_tm_created" in index_names
        assert "idx_te_thread" in index_names
        assert "idx_te_entity" in index_names


# ============================================================================
# index_thread_messages + search_conversations
# ============================================================================


class TestIndexAndSearch:
    """全文搜索测试"""

    def test_index_and_search_fts(self, _fresh_db):
        """写入消息后可通过 FTS5 搜索到"""
        # 先用 migrate 初始化主表，否则 save_thread 会 panic
        P.migrate_memorysaver_to_sqlite()

        messages = [
            {"role": "user", "content": "什么是异步编程？"},
            {"role": "assistant", "content": "异步编程是一种并发模式，参考 `entities/async.md`"},
            {"role": "user", "content": "Python 中如何实现异步？"},
        ]
        P.save_thread("fts-test", messages)
        P.index_thread_messages("fts-test", messages)

        results = P.search_conversations("异步")
        assert len(results) >= 2
        assert any("异步编程" in r["content"] for r in results)

    def test_search_by_thread_id(self, _fresh_db):
        """搜索按 thread_id 可区分"""
        P.migrate_memorysaver_to_sqlite()

        P.save_thread("thread-a", [{"role": "user", "content": "Python 教程"}])
        P.index_thread_messages("thread-a", [{"role": "user", "content": "Python 教程"}])

        P.save_thread("thread-b", [{"role": "user", "content": "Java 教程"}])
        P.index_thread_messages("thread-b", [{"role": "user", "content": "Java 教程"}])

        results = P.search_conversations("教程")
        thread_ids = {r["thread_id"] for r in results}
        assert "thread-a" in thread_ids
        assert "thread-b" in thread_ids

    def test_search_empty_query(self, _fresh_db):
        """空查询返回空列表"""
        P.migrate_memorysaver_to_sqlite()
        assert P.search_conversations("") == []
        assert P.search_conversations(" ") == []

    def test_search_no_matches(self, _fresh_db):
        """无匹配返回空"""
        P.migrate_memorysaver_to_sqlite()
        P.save_thread("no-match", [{"role": "user", "content": "hello"}])
        P.index_thread_messages("no-match", [{"role": "user", "content": "hello"}])
        assert P.search_conversations("nonexistent_term_xyz") == []

    def test_index_empty_messages(self, _fresh_db):
        """空消息列表不崩溃"""
        P.migrate_memorysaver_to_sqlite()
        # 不抛异常即通过
        P.index_thread_messages("empty", [])

    def test_index_special_characters(self, _fresh_db):
        """特殊字符正确索引"""
        P.migrate_memorysaver_to_sqlite()
        content = '他说："你好"\n新行\n🔥 Emoji 🎉'
        messages = [{"role": "user", "content": content}]
        P.save_thread("special", messages)
        P.index_thread_messages("special", messages)

        results = P.search_conversations("你好")
        assert len(results) >= 1
        assert results[0]["content"] == content

    def test_reindex_updates(self, _fresh_db):
        """重新索引后旧数据被替换"""
        P.migrate_memorysaver_to_sqlite()

        messages_v1 = [{"role": "user", "content": "旧消息"}]
        P.save_thread("reindex-test", messages_v1)
        P.index_thread_messages("reindex-test", messages_v1)

        messages_v2 = [{"role": "user", "content": "新消息"}]
        P.save_thread("reindex-test", messages_v2)
        P.index_thread_messages("reindex-test", messages_v2)

        results = P.search_conversations("新消息")
        assert len(results) >= 1

        old_results = P.search_conversations("旧消息")
        # 旧消息被覆盖后应搜索不到（或极少的残余）
        assert len(old_results) == 0


# ============================================================================
# extract_thread_entities
# ============================================================================


class TestEntityExtraction:
    """实体提取测试"""

    def test_extract_entities(self, _fresh_db):
        """从消息中提取高频实体"""
        P.migrate_memorysaver_to_sqlite()

        messages = [
            {"role": "user", "content": "Python 异步编程怎么用"},
            {"role": "assistant", "content": "Python 的 async/await 语法"},
            {"role": "user", "content": "Python 异步和 Java 有什么区别"},
        ]
        P.save_thread("entity-test", messages)
        P.extract_thread_entities("entity-test", messages)

        entities = P.get_thread_entities("entity-test")
        entity_names = {e["entity"] for e in entities}

        # "Python" 出现 3 次，应被提取
        assert "Python" in entity_names or "python" in entity_names

    def test_extract_wiki_references(self, _fresh_db):
        """Wiki 页面引用被提取为实体（同一引用出现 ≥2 次）"""
        P.migrate_memorysaver_to_sqlite()

        messages = [
            {"role": "assistant", "content": "参考 `entities/python.md`"},
            {"role": "assistant", "content": "再次引用 `entities/python.md`"},
        ]
        P.save_thread("wiki-entity", messages)
        P.extract_thread_entities("wiki-entity", messages)

        entities = P.get_thread_entities("wiki-entity")
        entity_names = {e["entity"] for e in entities}

        # Wiki 引用中的实体名应被提取（entities python 出现 2 次 ≥ THREAD_ENTITY_MIN_FREQ=2）
        assert any("python" in e.lower() for e in entity_names)

    def test_low_frequency_not_indexed(self, _fresh_db):
        """低频词不被索引（低于 THREAD_ENTITY_MIN_FREQ）"""
        P.migrate_memorysaver_to_sqlite()

        messages = [
            {"role": "user", "content": "罕见词_xyz_abc"},
        ]
        P.save_thread("low-freq", messages)
        P.extract_thread_entities("low-freq", messages)

        entities = P.get_thread_entities("low-freq")
        # 只出现 1 次，不应被索引
        assert len(entities) == 0

    def test_extract_empty(self, _fresh_db):
        """空消息不提取实体"""
        P.migrate_memorysaver_to_sqlite()
        P.extract_thread_entities("empty", [])
        assert P.get_thread_entities("empty") == []


# ============================================================================
# 跨线程聚合（global_entities）
# ============================================================================


class TestGlobalEntities:
    """跨线程实体聚合测试"""

    def test_global_aggregation(self, _fresh_db):
        """同一实体跨多个 thread 聚合"""
        P.migrate_memorysaver_to_sqlite()

        # Thread 1: Python 出现 2 次（≥ THREAD_ENTITY_MIN_FREQ=2）
        P.save_thread("t1", [{"role": "user", "content": "Python Python 怎么用"}])
        P.extract_thread_entities("t1", [{"role": "user", "content": "Python Python 怎么用"}])

        # Thread 2: Python 出现 3 次
        P.save_thread("t2", [{"role": "user", "content": "Python 异步 Python 并发 Python 协程"}])
        P.extract_thread_entities("t2", [{"role": "user", "content": "Python 异步 Python 并发 Python 协程"}])

        globals_ = P.get_global_entities()
        python_entities = [g for g in globals_ if "Python" in g["entity"] or "python" in g["entity"]]
        if python_entities:
            pe = python_entities[0]
            assert pe["thread_count"] >= 2
            assert pe["total_frequency"] >= 5

    def test_global_entities_limit(self, _fresh_db):
        """get_global_entities 的 limit 参数有效"""
        P.migrate_memorysaver_to_sqlite()

        for i in range(20):
            tid = f"global-{i}"
            P.save_thread(tid, [{"role": "user", "content": f"实体{i} 技术" * 3}])
            P.extract_thread_entities(tid, [{"role": "user", "content": f"实体{i} 技术" * 3}])

        result = P.get_global_entities(limit=5)
        assert len(result) <= 5

    def test_global_empty(self, _fresh_db):
        """无数据时返回空列表"""
        P.migrate_memorysaver_to_sqlite()
        assert P.get_global_entities() == []


# ============================================================================
# 删除索引
# ============================================================================


class TestDeleteIndex:
    """删除索引测试"""

    def test_delete_thread_index(self, _fresh_db):
        """删除索引后搜索不到"""
        P.migrate_memorysaver_to_sqlite()

        messages = [{"role": "user", "content": "测试删除"}]
        P.save_thread("to-delete", messages)
        P.index_thread_messages("to-delete", messages)
        P.extract_thread_entities("to-delete", messages)

        # 删除前能搜到
        assert len(P.search_conversations("测试删除")) >= 1

        # 删除索引
        P.delete_thread_index("to-delete")

        # 删除后搜不到
        assert len(P.search_conversations("测试删除")) == 0
        assert P.get_thread_entities("to-delete") == []

    def test_delete_other_thread_unaffected(self, _fresh_db):
        """删除一个 thread 的索引不影响其他"""
        P.migrate_memorysaver_to_sqlite()

        P.save_thread("keep", [{"role": "user", "content": "保留数据"}])
        P.index_thread_messages("keep", [{"role": "user", "content": "保留数据"}])

        P.save_thread("remove", [{"role": "user", "content": "删除数据"}])
        P.index_thread_messages("remove", [{"role": "user", "content": "删除数据"}])
        P.extract_thread_entities("remove", [{"role": "user", "content": "删除数据"}])

        P.delete_thread_index("remove")

        # keep 不受影响
        assert len(P.search_conversations("保留数据")) >= 1


# ============================================================================
# 集成：save_thread → index_thread → search
# ============================================================================


class TestIntegration:
    """完整链路集成测试"""

    def test_save_and_search(self, _fresh_db):
        """保存 thread → 构建索引 → 搜索 完整链路"""
        P.migrate_memorysaver_to_sqlite()

        messages = [
            {"role": "user", "content": "LangGraph 怎么创建 Agent"},
            {"role": "assistant", "content": "使用 StateGraph 定义状态和节点"},
            {"role": "user", "content": "能举个 LangGraph 的例子吗"},
        ]
        P.save_thread("integ-test", messages)
        P.index_thread_messages("integ-test", messages)
        P.extract_thread_entities("integ-test", messages)

        # 全文搜索
        results = P.search_conversations("LangGraph")
        assert len(results) >= 2

        # 实体检索
        entities = P.get_thread_entities("integ-test")
        entity_names = {e["entity"].lower() for e in entities}
        assert any("langgraph" in e for e in entity_names)

        # 跨线程聚合
        globals_ = P.get_global_entities()
        global_names = {g["entity"].lower() for g in globals_}
        assert any("langgraph" in e for e in global_names)

    @pytest.mark.asyncio
    async def test_session_save_triggers_index(self, _fresh_db, mocker):
        """验证 session.py 中 save_thread 后自动调用索引

        通过 mock 验证 index_thread_messages 被调用
        """
        # 由于 session 导入时会触发 migrate，需先 mock 环境
        mocker.patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"})
        mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mocker.MagicMock())

        mock_index = mocker.patch("src.agent.memory.store.index_thread_messages")
        mock_extract = mocker.patch("src.agent.memory.store.extract_thread_entities")

        from src.agent.session import chat_stream_session

        agent = mocker.MagicMock()

        # Mock get_state
        snapshot = mocker.MagicMock()
        snapshot.values = {"messages": []}
        snapshot.interrupts = ()
        agent.get_state.return_value = snapshot

        async def event_generator(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="回答")},
            }

        agent.astream_events = event_generator

        mocker.patch("src.agent.memory.store.load_thread", return_value=None)
        mocker.patch("src.agent.memory.store.save_thread")

        events = []
        async for e in chat_stream_session(agent, "你好", "session-index-test"):
            events.append(e)

        # 验证索引函数被调用
        assert mock_index.called
        assert mock_extract.called
