"""
系统管理路由测试 — 重置数据文件（reset-data）

验证：删除数据文件（wiki 页面/队列/对话历史/向量索引），
保留系统配置（API 密钥/模型配置/wiki-schema.md）。
"""
import os
import sqlite3


def _build_fake_data_dir(tmp_path):
    """构造假数据目录：wiki/ + raw/sources/ + wiki.db + 数据文件"""
    # wiki 目录（含 schema 和页面）
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (wiki / "wiki-schema.md").write_text("# 构建规范\n", encoding="utf-8")
    (wiki / "python.md").write_text("# Python\n", encoding="utf-8")

    # raw/sources（用户输入文件）
    sources = tmp_path / "raw" / "sources"
    sources.mkdir(parents=True)
    (sources / "input.txt").write_text("用户输入", encoding="utf-8")

    # wiki.db — 数据表 + 配置表混合
    db_path = tmp_path / "wiki.db"
    con = sqlite3.connect(db_path)
    con.executescript("""
        CREATE TABLE wiki_pages (id INTEGER PRIMARY KEY AUTOINCREMENT, slug TEXT, title TEXT);
        CREATE TABLE wiki_settings (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT);
        CREATE TABLE model_configs (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE ingest_queue (id INTEGER PRIMARY KEY, path TEXT);
        CREATE TABLE task_queue (id INTEGER PRIMARY KEY, task TEXT);
        CREATE TABLE graph_cache (id INTEGER PRIMARY KEY);
        CREATE TABLE graph_relevance (id INTEGER PRIMARY KEY);
        CREATE TABLE ingest_cache (id INTEGER PRIMARY KEY);
        CREATE TABLE lint_cache (id INTEGER PRIMARY KEY);
        CREATE TABLE token_usage_log (id INTEGER PRIMARY KEY);
        CREATE TABLE operation_log (id INTEGER PRIMARY KEY);
        CREATE TABLE page_links (id INTEGER PRIMARY KEY);
    """)
    con.execute("INSERT INTO wiki_pages (slug, title) VALUES ('python', 'Python')")
    con.execute("INSERT INTO ingest_queue (path) VALUES ('raw/sources/input.txt')")
    con.execute("INSERT INTO task_queue (task) VALUES ('rebuild_graph')")
    con.execute("INSERT INTO graph_cache (id) VALUES (1)")
    con.execute("INSERT INTO graph_relevance (id) VALUES (1)")
    con.execute("INSERT INTO ingest_cache (id) VALUES (1)")
    con.execute("INSERT INTO lint_cache (id) VALUES (1)")
    con.execute("INSERT INTO token_usage_log (id) VALUES (1)")
    con.execute("INSERT INTO operation_log (id) VALUES (1)")
    con.execute("INSERT INTO page_links (id) VALUES (1)")
    con.execute(
        "INSERT INTO wiki_settings (key, value) VALUES ('settings.deepseek_api_key', '\"sk-test\"')"
    )
    con.execute("INSERT INTO model_configs (name) VALUES ('主模型')")
    con.commit()
    con.close()

    # agent_persistence.db（对话记忆，建表 + 数据）
    mem_db = tmp_path / "agent_persistence.db"
    con2 = sqlite3.connect(mem_db)
    con2.executescript("""
        CREATE TABLE agent_threads (thread_id TEXT PRIMARY KEY, title TEXT);
        CREATE TABLE thread_messages (id INTEGER PRIMARY KEY, thread_id TEXT);
        CREATE TABLE thread_entities (id INTEGER PRIMARY KEY);
        CREATE TABLE global_entities (id INTEGER PRIMARY KEY);
        CREATE TABLE agent_feedback (id INTEGER PRIMARY KEY);
    """)
    con2.execute("INSERT INTO agent_threads (thread_id, title) VALUES ('t1', '旧对话')")
    con2.execute("INSERT INTO thread_messages (thread_id) VALUES ('t1')")
    con2.commit()
    con2.close()

    # checkpoints.db（LangGraph checkpoint，建表 + 数据）
    ck_db = tmp_path / "checkpoints.db"
    con3 = sqlite3.connect(ck_db)
    con3.executescript("""
        CREATE TABLE checkpoints (thread_id TEXT PRIMARY KEY);
        CREATE TABLE writes (id INTEGER PRIMARY KEY);
    """)
    con3.execute("INSERT INTO checkpoints (thread_id) VALUES ('t1')")
    con3.commit()
    con3.close()

    (tmp_path / "chroma_db").mkdir()
    return db_path


def _isolate_paths(tmp_path, monkeypatch):
    """把 system 模块的路径解析隔离到 tmp_path"""
    monkeypatch.setattr("src.api.routes.system.get_wiki_dir", lambda: str(tmp_path / "wiki"))
    monkeypatch.setattr(
        "src.api.routes.system.get_raw_sources_dir", lambda: str(tmp_path / "raw" / "sources")
    )
    monkeypatch.setattr("src.api.routes.system.get_db_path", lambda name="wiki.db": str(tmp_path / name))
    monkeypatch.setattr("src.api.routes.system.get_app_dir", lambda: str(tmp_path))


class TestSystemResetData:
    """重置数据文件接口 — 删数据、留配置"""

    def test_reset_data_clears_data_keeps_config(self, client, tmp_path, monkeypatch):
        """数据表清空、配置表保留、schema 保留、数据文件删除"""
        db_path = _build_fake_data_dir(tmp_path)
        _isolate_paths(tmp_path, monkeypatch)

        resp = client.post("/v1/system/reset-data")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

        # 1. wiki/ 只保留 schema 规范
        assert os.listdir(tmp_path / "wiki") == ["wiki-schema.md"]

        # 2. raw/sources 清空
        assert os.listdir(tmp_path / "raw" / "sources") == []

        # 3. 对话记忆/checkpoint 表级清空（文件保留，防止持有连接的实例写回旧数据）
        mem_con = sqlite3.connect(tmp_path / "agent_persistence.db")
        for t in ["agent_threads", "thread_messages", "thread_entities", "global_entities", "agent_feedback"]:
            assert mem_con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
        mem_con.close()
        ck_con = sqlite3.connect(tmp_path / "checkpoints.db")
        for t in ["checkpoints", "writes"]:
            assert ck_con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0, t
        ck_con.close()

        # 向量索引目录删除（重启自动重建）
        assert not (tmp_path / "chroma_db").exists()

        # 4. 配置保留
        con = sqlite3.connect(db_path)
        settings = dict(con.execute("SELECT key, value FROM wiki_settings"))
        assert settings.get("settings.deepseek_api_key") == '"sk-test"'
        assert con.execute("SELECT COUNT(*) FROM model_configs").fetchone()[0] == 1

        # 5. 数据表清空
        for table in [
            "wiki_pages", "page_links", "ingest_queue", "task_queue",
            "graph_cache", "graph_relevance", "ingest_cache", "lint_cache",
            "token_usage_log", "operation_log",
        ]:
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count == 0, f"{table} 未清空: {count} 行"

        # 6. 自增序列重置
        assert con.execute("SELECT COUNT(*) FROM sqlite_sequence").fetchone()[0] == 0
        con.close()

    def test_reset_data_without_db(self, client, tmp_path, monkeypatch):
        """无 wiki.db 时也能正常返回"""
        (tmp_path / "wiki").mkdir()
        _isolate_paths(tmp_path, monkeypatch)

        resp = client.post("/v1/system/reset-data")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
