"""
BM25 关键词搜索 — 标题加权 + Bigram 分词

比 SQLite LIKE 更精确：词频（TF）× 逆文档频率（IDF）
比向量搜索更快：纯内存计算，零 API 调用

依赖：rank_bm25（纯 Python，零 C 扩展）
"""
import logging
import os

from rank_bm25 import BM25Okapi

from src.core.search.bigram import build_searchable_tokens

logger = logging.getLogger("search.bm25")


class BM25Search:
    """BM25 关键词搜索索引

    生命周期：
      1. build_index(pages) — 启动时构建
      2. search(query) — 搜索
      3. mark_dirty() — ingest 后标记脏
      4. build_index() 下次搜索前重建（懒重建）

    线程安全：当前为单线程，未加锁。
    """

    def __init__(self) -> None:
        self._index: BM25Okapi | None = None
        self._corpus: list[str] = []       # 原文（用于摘要）
        self._paths: list[str] = []         # 页面路径
        self._dirty = True                  # 是否需要重建

    # ------------------------------------------------------------------
    # 索引构建
    # ------------------------------------------------------------------

    def build_index(self, pages: list[dict]) -> None:
        """从页面列表构建 BM25 索引

        Args:
            pages: [{path, title, content}, ...]
        """
        self._corpus = []
        self._paths = []
        tokenized_corpus: list[list[str]] = []

        for p in pages:
            path = p.get("path", "")
            title = p.get("title", "")
            content = p.get("content", "")
            self._paths.append(path)
            self._corpus.append(content)

            tokens = build_searchable_tokens(content, title=title)
            tokenized_corpus.append(tokens)

        self._index = BM25Okapi(tokenized_corpus)
        self._dirty = False

        logger.info(
            "BM25 索引构建完成 | pages=%d tokens=%d",
            len(self._paths), sum(len(t) for t in tokenized_corpus),
        )

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    def search(self, query: str, k: int = 10) -> list[dict]:
        """BM25 搜索

        Args:
            query: 搜索关键词
            k: 最大返回条数

        Returns:
            [{"path": "...", "score": 0.85, "title": "...", "snippet": "..."}, ...]
            索引为空或未构建时返回空列表。
        """
        if not self._index or self._dirty:
            return []

        tokens = build_searchable_tokens(query)
        if not tokens:
            return []

        scores = self._index.get_scores(tokens)
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:k]

        results = []
        for idx in top_indices:
            results.append({
                "path": self._paths[idx],
                "score": round(float(scores[idx]), 4),
                "snippet": self._corpus[idx][:150].replace("\n", " "),
            })

        return results

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def mark_dirty(self) -> None:
        """标记索引为脏（在 ingest 后调用）"""
        self._dirty = True
        self._index = None

    @property
    def is_built(self) -> bool:
        return self._index is not None and not self._dirty

    @property
    def page_count(self) -> int:
        return len(self._paths)

    def clear(self) -> None:
        """清空索引"""
        self._index = None
        self._corpus = []
        self._paths = []
        self._dirty = True
