"""
搜索引擎降级测试 — 语义搜索不可用时自动回退 BM25

当前版本语义搜索整体关闭（依赖未内置），vector/hybrid 请求必须
降级为普通关键词搜索，不返回空结果、不伪标搜索方式。
"""
from src.core.search.engine import SearchEngine


class DisabledEngine:
    """禁用态 embedding 引擎（开关关闭 / 依赖缺失 / 初始化失败）"""

    enabled = False
    chunk_collection = None

    def search(self, query: str, k: int = 10) -> list[dict]:
        return []


class EnabledEngine:
    """可用态 embedding 引擎（未来版本恢复后路径）"""

    enabled = True
    chunk_collection = None

    def search(self, query: str, k: int = 10) -> list[dict]:
        return [{"path": "v.md", "score": 0.9}]


def _mk_engine() -> SearchEngine:
    """构造已初始化 + BM25 已 mock 的引擎（聚焦降级路径）"""
    engine = SearchEngine()
    engine._initialized = True
    engine._search_bm25 = lambda q, k: (  # type: ignore[method-assign]
        [{"path": "k.md", "score": 0.7, "search_method": "bm25"}], 1,
    )
    return engine


def test_vector_falls_back_to_bm25(monkeypatch):
    """向量搜索不可用 → 降级为 BM25 结果"""
    engine = _mk_engine()
    monkeypatch.setattr("src.core.embedding.get_embedding_engine", lambda: DisabledEngine())

    results = engine._search_vector("测试", k=10)
    assert len(results) == 1
    assert results[0]["path"] == "k.md"
    assert results[0]["search_method"] == "bm25"


def test_hybrid_falls_back_to_bm25(monkeypatch):
    """混合搜索不可用 → 降级为纯 BM25（不伪标 hybrid）"""
    engine = _mk_engine()
    monkeypatch.setattr("src.core.embedding.get_embedding_engine", lambda: DisabledEngine())

    results = engine._search_hybrid("测试", k=10)
    assert len(results) == 1
    assert results[0]["path"] == "k.md"
    assert results[0]["search_method"] == "bm25"


def test_vector_uses_engine_when_enabled(monkeypatch):
    """引擎可用时走正常向量路径（未来版本恢复路径不被破坏）"""
    engine = _mk_engine()
    monkeypatch.setattr("src.core.embedding.get_embedding_engine", lambda: EnabledEngine())

    results = engine._search_vector("测试", k=10)
    assert len(results) == 1
    assert results[0]["path"] == "v.md"
    assert results[0]["search_method"] == "vector"


def test_hybrid_uses_engine_when_enabled(monkeypatch):
    """引擎可用时混合搜索正常 RRF 融合"""
    engine = _mk_engine()
    monkeypatch.setattr("src.core.embedding.get_embedding_engine", lambda: EnabledEngine())

    results = engine._search_hybrid("测试", k=10)
    assert len(results) >= 1
    assert results[0]["search_method"] == "hybrid"
