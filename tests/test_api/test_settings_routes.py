"""
设置接口测试 — 语义搜索开关 embedding_enabled

验证：默认关闭（False）、POST 保存后 GET 可回读（设置页热生效）。
"""
import json


def _isolate_db(tmp_path, monkeypatch):
    """隔离 wiki.db 到 tmp_path（repository 模块内引用 get_db_path）"""
    monkeypatch.setattr(
        "src.db.repository.get_db_path", lambda name="wiki.db": str(tmp_path / name)
    )


class TestEmbeddingEnabledSetting:
    """embedding_enabled 设置字段"""

    def test_default_false(self, client, tmp_path, monkeypatch):
        """默认关闭语义搜索"""
        _isolate_db(tmp_path, monkeypatch)
        resp = client.get("/v1/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert "embedding_enabled" in body
        assert body["embedding_enabled"] is False

    def test_roundtrip_save_and_read(self, client, tmp_path, monkeypatch):
        """设置页保存 true 后 GET 可回读（无需重启）"""
        _isolate_db(tmp_path, monkeypatch)
        resp = client.post("/v1/settings", json={"embedding_enabled": True})
        assert resp.status_code == 200
        assert resp.json()["embedding_enabled"] is True

        resp2 = client.get("/v1/settings")
        assert resp2.status_code == 200
        assert resp2.json()["embedding_enabled"] is True

    def test_turn_off_again(self, client, tmp_path, monkeypatch):
        """开启后可再关闭"""
        _isolate_db(tmp_path, monkeypatch)
        client.post("/v1/settings", json={"embedding_enabled": True})
        client.post("/v1/settings", json={"embedding_enabled": False})
        resp = client.get("/v1/settings")
        assert resp.json()["embedding_enabled"] is False

    def test_db_value_is_json_parsed(self, client, tmp_path, monkeypatch):
        """DB 中存储的 JSON 值能正确解析回 bool"""
        _isolate_db(tmp_path, monkeypatch)
        from src.db.repository import WikiRepository

        repo = WikiRepository(db_path=str(tmp_path / "wiki.db"))
        repo.set_setting("settings.embedding_enabled", json.dumps(True))
        resp = client.get("/v1/settings")
        assert resp.json()["embedding_enabled"] is True
