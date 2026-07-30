"""
向量嵌入引擎 — Chroma + sentence-transformers 本地模型

提供两套向量索引：
  1. wiki_pages — 整页编码（原有，保持兼容）
  2. wiki_chunks — 章节级 chunk 编码（新增，需要 CHUNK_SEARCH_ENABLED）

根据配置开关（EMBEDDING_ENABLED）决定是否启用。
使用本地模型，无需 API 调用，隐私安全，离线可用。
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

    Chroma 含两个 collection：
      - wiki_pages（原有）：整页编码，pages 级别的向量搜索
      - wiki_chunks（新增）：章节级 chunk 编码，精细粒度搜索

    chunk 搜索通过配置 CHUNK_SEARCH_ENABLED 开启关闭，默认关闭。
    """

    def __init__(self) -> None:
        self.enabled = settings.embedding_enabled
        if not self.enabled:
            logger.info("Embedding 引擎未启用（EMBEDDING_ENABLED=false）")
            self.client = None
            self.collection = None
            self.chunk_collection = None
            self._model = None
            return

        try:
            self.client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
            # 原有 — 整页 collection
            self.collection = self.client.get_or_create_collection(
                name="wiki_pages",
                metadata={"hnsw:space": "cosine"},
            )
            # 新增 — chunk collection
            self.chunk_collection = self.client.get_or_create_collection(
                name="wiki_chunks",
                metadata={"hnsw:space": "cosine"},
            )

            model_path = settings.embedding_model_path
            if not os.path.isdir(model_path):
                logger.warning("Embedding 模型路径不存在，尝试在线加载 | path=%s", model_path)
            self._model = SentenceTransformer(model_path)
            logger.info(
                "Embedding 引擎已初始化 | dir=%s model=%s chunks=%s",
                settings.chroma_persist_dir, model_path,
                settings.chunk_search_enabled,
            )
        except Exception as exc:
            logger.error("Embedding 引擎初始化失败 | %s", exc)
            self.enabled = False
            self.client = None
            self.collection = None
            self.chunk_collection = None
            self._model = None

    # ------------------------------------------------------------------
    # 页面索引（原有，保持兼容）
    # ------------------------------------------------------------------

    def embed_page(self, path: str, content: str) -> None:
        """为单个页面生成向量并 upsert 到 Chroma (wiki_pages)

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
    # Chunk 索引（新增）
    # ------------------------------------------------------------------

    def embed_page_chunks(self, path: str, chunks: list) -> None:
        """为页面的章节 chunk 生成向量并 upsert 到 Chroma (wiki_chunks)

        先删除该页面旧 chunk，再插入新 chunk（全量替换，简单可靠）。

        Args:
            path: wiki 页面路径
            chunks: chunk_page() 返回的 Chunk 列表
        """
        if not self._ready():
            return

        # 先删旧 chunk
        self.delete_page_chunks(path)

        if not chunks:
            return

        try:
            ids: list[str] = []
            embeddings: list[list[float]] = []
            metadatas: list[dict] = []

            for c in chunks:
                text = c.content[:8000]
                if not text.strip():
                    continue
                vector = self._model.encode(text).tolist()
                ids.append(c.id)
                embeddings.append(vector)
                metadatas.append(c.to_metadata())

            if ids:
                self.chunk_collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    metadatas=metadatas,
                )
                logger.debug(
                    "Chunk embedding 更新 | path=%s chunks=%d", path, len(ids),
                )
        except Exception as exc:
            logger.warning("Chunk embedding 失败 | path=%s error=%s", path, exc)

    def delete_page_chunks(self, path: str) -> None:
        """删除一个页面的所有 chunk 向量

        通过 metadata 过滤 path 字段来批量删除。
        """
        if not self._ready():
            return
        try:
            self.chunk_collection.delete(where={"path": path})
        except Exception as exc:
            logger.debug(
                "Chunk embedding 删除跳过（可能不存在）| path=%s %s", path, exc,
            )

    def search_chunks(self, query: str, k: int = 10) -> list[dict]:
        """Chunk 级语义搜索

        Args:
            query: 搜索关键词
            k: 最大返回条数

        Returns:
            [{"chunk_id": "...", "path": "...", "score": 0.85,
              "heading": "...", "breadcrumb": "...", ...}, ...]
            引擎未启用时返回空列表。
        """
        if not self._ready():
            return []

        try:
            qvec = self._model.encode(query).tolist()
            results = self.chunk_collection.query(
                query_embeddings=[qvec],
                n_results=k,
            )

            items: list[dict] = []
            for i, doc_id in enumerate(results["ids"][0]):
                meta: dict = results["metadatas"][0][i] if results.get("metadatas") else {}
                items.append({
                    "chunk_id": doc_id,
                    "path": meta.get("path", doc_id),
                    "score": round(1 - results["distances"][0][i], 4) if results.get("distances") else 0,
                    "heading": meta.get("heading", ""),
                    "breadcrumb": meta.get("breadcrumb", ""),
                    "start_line": meta.get("start_line", 0),
                    "end_line": meta.get("end_line", 0),
                    "chunk_index": meta.get("chunk_index", 0),
                    "total_chunks": meta.get("total_chunks", 1),
                    "page_hash": meta.get("page_hash", ""),
                    "metadata": meta,
                })
            return items

        except Exception as exc:
            logger.warning("Chunk 语义搜索失败 | query=%s error=%s", query, exc)
            return []

    # ------------------------------------------------------------------
    # 语义搜索（整页级别，原有兼容）
    # ------------------------------------------------------------------

    def search(self, query: str, k: int = 10) -> list[dict]:
        """整页级语义搜索（wiki_pages collection）

        Args:
            query: 搜索关键词
            k: 最大返回条数

        Returns:
            [{"path": "...", "score": 0.85, "metadata": {...}}, ...]
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
        """返回 wiki_pages 索引的向量数量"""
        if not self._ready():
            return 0
        try:
            return self.collection.count()
        except Exception:
            return 0

    def chunk_count(self) -> int:
        """返回 wiki_chunks 索引的向量数量"""
        if not self._ready():
            return 0
        try:
            return self.chunk_collection.count()
        except Exception:
            return 0

    def _ready(self) -> bool:
        """检查引擎是否可用"""
        return self.enabled and self.collection is not None and self._model is not None
