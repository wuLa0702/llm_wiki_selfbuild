"""
向量嵌入引擎 — Chroma + sentence-transformers 本地模型

根据配置开关（EMBEDDING_ENABLED）决定是否启用。
使用本地模型，无需 API 调用，隐私安全，离线可用。
ingest 后自动为新/更新的页面生成向量，支持语义搜索。

依赖：chromadb, sentence-transformers, huggingface_hub
"""
import logging
import os

import chromadb
from sentence_transformers import SentenceTransformer

from src.config import settings

logger = logging.getLogger("embedding")

_engine: "EmbeddingEngine | None" = None


def get_embedding_engine() -> "EmbeddingEngine":
    """获取全局 EmbeddingEngine 单例"""
    global _engine
    if _engine is None:
        _engine = EmbeddingEngine()
    return _engine


class EmbeddingEngine:
    """向量嵌入引擎 — Chroma + 本地 sentence-transformers 模型

    通过 config.embedding_enabled 全局开关控制。
    关闭时所有方法静默跳过。
    """

    def __init__(self) -> None:
        self.enabled = settings.embedding_enabled
        if not self.enabled:
            logger.info("Embedding 引擎未启用（EMBEDDING_ENABLED=false）")
            self.client = None
            self.collection = None
            self._model = None
            return

        try:
            self.client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
            self.collection = self.client.get_or_create_collection(
                name="wiki_pages",
                metadata={"hnsw:space": "cosine"},
            )

            model_path = settings.embedding_model_path
            if not os.path.isdir(model_path):
                logger.warning("Embedding 模型路径不存在，尝试在线加载 | path=%s", model_path)
            self._model = SentenceTransformer(model_path)
            logger.info(
                "Embedding 引擎已初始化 | dir=%s model=%s",
                settings.chroma_persist_dir, model_path,
            )
        except Exception as exc:
            logger.error("Embedding 引擎初始化失败 | %s", exc)
            self.enabled = False
            self.client = None
            self.collection = None
            self._model = None

    # ------------------------------------------------------------------
    # 页面索引
    # ------------------------------------------------------------------

    def embed_page(self, path: str, content: str) -> None:
        """为单个页面生成向量并 upsert 到 Chroma

        Args:
            path: wiki 页面路径（如 entities/python.md）
            content: 页面 Markdown 内容
        """
        if not self._ready():
            return

        try:
            text = content[:8000]
            vector = self._model.encode(text).tolist()
            self.collection.upsert(
                ids=[path],
                embeddings=[vector],
                metadatas=[{"path": path, "length": len(content)}],
            )
            logger.debug("Embedding 更新 | path=%s length=%d", path, len(content))
        except Exception as exc:
            logger.warning("Embedding 失败 | path=%s error=%s", path, exc)

    def delete_page(self, path: str) -> None:
        """删除页面的向量

        当 wiki 页面被删除时调用此方法清理对应向量。
        """
        if not self._ready():
            return
        try:
            self.collection.delete(ids=[path])
        except Exception as exc:
            logger.debug("Embedding 删除跳过（可能不存在）| path=%s %s", path, exc)

    # ------------------------------------------------------------------
    # 语义搜索
    # ------------------------------------------------------------------

    def search(self, query: str, k: int = 10) -> list[dict]:
        """语义搜索

        Args:
            query: 搜索关键词
            k: 最大返回条数

        Returns:
            [{"path": "entities/python.md", "score": 0.85, "metadata": {...}}, ...]
            引擎未启用时返回空列表。
        """
        if not self._ready():
            return []

        try:
            qvec = self._model.encode(query).tolist()
            results = self.collection.query(
                query_embeddings=[qvec],
                n_results=k,
            )

            items: list[dict] = []
            for i, doc_id in enumerate(results["ids"][0]):
                items.append({
                    "path": doc_id,
                    "score": round(1 - results["distances"][0][i], 4) if results.get("distances") else 0,
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                })
            return items

        except Exception as exc:
            logger.warning("语义搜索失败 | query=%s error=%s", query, exc)
            return []

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def count(self) -> int:
        """返回索引的向量数量"""
        if not self._ready():
            return 0
        try:
            return self.collection.count()
        except Exception:
            return 0

    def _ready(self) -> bool:
        """检查引擎是否可用"""
        return self.enabled and self.collection is not None and self._model is not None
