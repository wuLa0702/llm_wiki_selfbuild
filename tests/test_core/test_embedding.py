"""
Embedding 引擎开关测试 — DB wiki_settings 控制 + 模型完整性检查

验证：
  1. 开关关闭（默认）→ 引擎禁用，不加载模型（不触发任何下载）
  2. 开关开启 + 模型完整 → 正常初始化，模型加载带 local_files_only=True
  3. 开关开启 + 模型缺失/不完整 → 快速降级禁用，绝不触发在线下载
  4. 运行中关闭开关 → 热生效（旧引擎被丢弃）
"""
import json

import pytest

from src.core import embedding as embedding_mod


class FakeCollection:
    """最小 Chroma collection 假件"""

    def __init__(self, name: str = "") -> None:
        self.name = name

    def upsert(self, **kwargs) -> None:
        pass

    def delete(self, **kwargs) -> None:
        pass

    def count(self) -> int:
        return 0

    def query(self, **kwargs):
        return {"ids": [[]], "distances": [[]], "metadatas": [[]]}


class FakeChromaClient:
    """最小 Chroma PersistentClient 假件"""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def get_or_create_collection(self, name: str = "", **kwargs):
        return FakeCollection(name)


class ModelLoaderRecorder:
    """记录 SentenceTransformer 调用（断言是否加载/参数）"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return _FakeModel()


class _FakeModel:
    def encode(self, text):
        return [0.1, 0.2, 0.3]


@pytest.fixture(autouse=True)
def _reset_engine_singleton():
    """每个测试后重置模块级单例，避免跨测试污染"""
    embedding_mod._engine = None
    yield
    embedding_mod._engine = None


def _isolate(tmp_path, monkeypatch, enabled: bool):
    """隔离 DB（写入开关）+ 隔离 chroma/模型加载器"""
    monkeypatch.setattr(
        "src.db.repository.get_db_path", lambda name="wiki.db": str(tmp_path / "wiki.db")
    )
    from src.db.repository import WikiRepository

    repo = WikiRepository(db_path=str(tmp_path / "wiki.db"))
    repo.set_setting("settings.embedding_enabled", json.dumps(enabled))

    recorder = ModelLoaderRecorder()
    monkeypatch.setattr(embedding_mod, "SentenceTransformer", recorder)
    monkeypatch.setattr(embedding_mod.chromadb, "PersistentClient", FakeChromaClient)
    monkeypatch.setattr(
        "src.config.settings.chunk_search_enabled", False
    )
    return recorder


def _make_model_dir(tmp_path, complete: bool) -> str:
    """构造模型目录：complete=True 时含 config.json + 权重文件"""
    model_dir = tmp_path / ".models" / "all-MiniLM-L6-v2"
    model_dir.mkdir(parents=True)
    if complete:
        (model_dir / "config.json").write_text("{}", encoding="utf-8")
        (model_dir / "model.safetensors").write_bytes(b"fake-weights")
    return str(model_dir)


class TestEmbeddingSwitch:
    """开关控制引擎行为"""

    def test_off_default_no_model_load(self, tmp_path, monkeypatch):
        """关闭时引擎禁用，不加载模型"""
        _isolate(tmp_path, monkeypatch, enabled=False)
        engine = embedding_mod.get_embedding_engine()
        assert engine.enabled is False
        assert engine._model is None

    def test_on_with_complete_model_loads_locally(self, tmp_path, monkeypatch):
        """开启 + 模型完整 → 初始化成功，local_files_only=True 防在线下载"""
        recorder = _isolate(tmp_path, monkeypatch, enabled=True)
        model_dir = _make_model_dir(tmp_path, complete=True)
        monkeypatch.setattr("src.config.settings.embedding_model_path", model_dir)

        engine = embedding_mod.get_embedding_engine()
        assert engine.enabled is True
        assert engine._model is not None
        assert len(recorder.calls) == 1
        args, kwargs = recorder.calls[0]
        assert args[0] == model_dir
        assert kwargs.get("local_files_only") is True

    def test_on_with_incomplete_model_degrades_offline(self, tmp_path, monkeypatch):
        """开启 + 模型目录空壳 → 快速降级禁用，不触发在线下载"""
        recorder = _isolate(tmp_path, monkeypatch, enabled=True)
        model_dir = _make_model_dir(tmp_path, complete=False)
        monkeypatch.setattr("src.config.settings.embedding_model_path", model_dir)

        engine = embedding_mod.get_embedding_engine()
        assert engine.enabled is False
        assert engine._model is None
        # 关键：绝不调用 SentenceTransformer（不触发 HuggingFace 在线下载）
        assert recorder.calls == []

    def test_hot_switch_off_after_init(self, tmp_path, monkeypatch):
        """初始化后关闭开关 → 立即热生效（返回禁用引擎）"""
        _isolate(tmp_path, monkeypatch, enabled=True)
        model_dir = _make_model_dir(tmp_path, complete=True)
        monkeypatch.setattr("src.config.settings.embedding_model_path", model_dir)

        engine = embedding_mod.get_embedding_engine()
        assert engine.enabled is True

        # 运行中关闭开关
        from src.db.repository import WikiRepository

        repo = WikiRepository(db_path=str(tmp_path / "wiki.db"))
        repo.set_setting("settings.embedding_enabled", json.dumps(False))

        engine2 = embedding_mod.get_embedding_engine()
        assert engine2.enabled is False

    def test_hot_switch_on_after_off(self, tmp_path, monkeypatch):
        """关闭后开启开关 → 按新配置初始化"""
        recorder = _isolate(tmp_path, monkeypatch, enabled=False)
        assert embedding_mod.get_embedding_engine().enabled is False

        from src.db.repository import WikiRepository

        repo = WikiRepository(db_path=str(tmp_path / "wiki.db"))
        repo.set_setting("settings.embedding_enabled", json.dumps(True))
        model_dir = _make_model_dir(tmp_path, complete=True)
        monkeypatch.setattr("src.config.settings.embedding_model_path", model_dir)

        engine = embedding_mod.get_embedding_engine()
        assert engine.enabled is True
        assert len(recorder.calls) == 1
