"""
统一搜索引擎 — BM25 关键词 + 向量语义 + RRF 融合

支持两种向量搜索模式：
  - page 模式（默认）：整页级向量搜索（wiki_pages collection）
  - chunk 模式（CHUNK_SEARCH_ENABLED=true）：章节级 chunk 搜索（wiki_chunks），
    结果聚合并换算 page 级 score

生命周期：
  1. 服务启动时 initialize() → 扫描所有 wiki 页面构建 BM25 索引
  2. ingest 后 mark_dirty() → 下次搜索前自动重建
  3. API 调 search() → BM25 / vector / hybrid 三种模式
"""
import logging
import os
from pathlib import Path

from src.config import settings
from src.core.search.bm25_search import BM25Search

logger = logging.getLogger("search.engine")

_engine: "SearchEngine | None" = None


def get_search_engine() -> "SearchEngine":
    """获取全局 SearchEngine 单例"""
    global _engine
    if _engine is None:
        _engine = SearchEngine()
    return _engine


class SearchEngine:
    """统一搜索入口 — 策略模式"""

    def __init__(self) -> None:
        self.bm25 = BM25Search()
        self._initialized = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def initialize(self, wiki_dir: str = "wiki") -> None:
        """服务启动时构建索引

        Args:
            wiki_dir: wiki 目录路径
        """
        pages = self._collect_pages(wiki_dir)
        if not pages:
            logger.info("搜索索引初始化跳过（无页面）| dir=%s", wiki_dir)
            self._initialized = True
            return

        self.bm25.build_index(pages)
        self._initialized = True
        logger.info("搜索引擎初始化完成 | pages=%d", len(pages))

    def mark_dirty(self) -> None:
        """标记索引为脏（ingest 后调用，下次搜索前懒重建）"""
        self.bm25.mark_dirty()

    # ------------------------------------------------------------------
    # 搜索
    # ------------------------------------------------------------------

    def search(
        self, query: str, method: str = "bm25", k: int = 10, offset: int = 0,
    ) -> tuple[list[dict], int]:
        """统一搜索入口

        Args:
            query: 搜索关键词
            method: 搜索模式 — bm25 / vector / hybrid
            k: 每页返回条数
            offset: 偏移量（用于翻页，0=第一页）

        Returns:
            (results, total_matched)
            results: [{"path": "...", "score": 0.72, ...}, ...]
            total_matched: 匹配文档总数（用于计算总页数）
        """
        if not self._initialized:
            return [], 0

        query = query.strip()
        if not query:
            return [], 0

        total_matched = 0
        total_needed = k + offset

        if method == "bm25":
            results, total_matched = self._search_bm25(query, k=total_needed)
        elif method == "vector":
            results = self._search_vector(query, k=total_needed)
            total_matched = len(results)
        elif method == "hybrid":
            results = self._search_hybrid(query, k=total_needed)
            total_matched = len(results)
        else:
            logger.warning("未知搜索模式 | method=%s", method)
            return [], 0

        # 翻页切片
        sliced = results[offset:offset + k]
        return sliced, total_matched

    def _rebuild_bm25_if_dirty(self) -> bool:
        """如果 BM25 索引脏，扫描 wiki/ 目录重建

        Returns:
            True 重建成功或无需重建，False 重建失败
        """
        if self.bm25.is_built:
            return True
        logger.info("BM25 索引脏，自动重建...")
        try:
            pages = self._collect_pages("wiki")
            if pages:
                self.bm25.build_index(pages)
                logger.info("BM25 索引重建完成 | pages=%d", len(pages))
            else:
                self.bm25._dirty = False
            return True
        except Exception:
            logger.exception("BM25 索引重建失败")
            return False

    def _search_bm25(self, query: str, k: int = 10) -> tuple[list[dict], int]:
        """纯 BM25 搜索（自动重建脏索引）

        Returns:
            (results, total_matched)
        """
        if not self._rebuild_bm25_if_dirty():
            return [], 0
        results, total_matched = self.bm25.search(query, k=k)
        results = _normalize_scores(results)
        for r in results:
            r["search_method"] = "bm25"
        return results, total_matched

    def _search_vector(self, query: str, k: int = 10) -> list[dict]:
        """向量搜索 — 根据配置选择 page 级或 chunk 级

        当 CHUNK_SEARCH_ENABLED=true 时，使用 chunk 级搜索（wiki_chunks），
        结果按 path 聚合到 page 级。

        语义搜索不可用（未启用/依赖未安装/引擎降级）时：
        自动降级为 BM25 关键词搜索，不返回空结果。
        """
        try:
            from src.core.embedding import get_embedding_engine

            engine = get_embedding_engine()

            if not engine.enabled:
                logger.warning("语义搜索不可用，向量搜索降级为关键词搜索 | query=%s", query)
                results, _ = self._search_bm25(query, k=k)
                for r in results:
                    r["search_method"] = "bm25"
                return results

            if settings.chunk_search_enabled and engine.chunk_collection is not None:
                return self._search_vector_chunks(engine, query, k)

            # 默认：整页级搜索
            results = engine.search(query, k=k)
            results = _normalize_scores(results)
            for r in results:
                r["search_method"] = "vector"
                r.setdefault("title", "")
                r["match_positions"] = []
            return results
        except Exception:
            logger.exception("向量搜索失败")
            return []

    def _search_vector_chunks(
        self, engine, query: str, k: int = 10,
    ) -> list[dict]:
        """Chunk 级向量搜索 → 聚合并到 page 级

        策略：
          1. 搜索 wiki_chunks，返回 chunk 级结果
          2. 按 path 分组聚合：
             - 页面最高分 = max(chunk_scores)
             - 多 chunk 命中加成 = 0.15 × (命中数 / 总chunk数)
             - 聚合 score = max_score + bonus
          3. 保留 top chunk 的 heading/breadcrumb 作为 match_positions

        Args:
            engine: EmbeddingEngine 实例
            query: 搜索关键词
            k: 期望返回的页面数（实际请求更多 chunk 以覆盖）

        Returns:
            页面级结果列表，含增强的 match_positions
        """
        from collections import defaultdict

        # 请求更多 chunk 以保证覆盖所有候选页面
        chunk_k = min(k * 3, 100)
        chunk_results = engine.search_chunks(query, k=chunk_k)
        if not chunk_results:
            return []

        # 按 path 聚合
        page_data: dict[str, dict] = {}
        path_match_positions: dict[str, list[dict]] = defaultdict(list)

        for cr in chunk_results:
            path = cr["path"]
            if path not in page_data:
                page_data[path] = {
                    "path": path,
                    "max_score": cr["score"],
                    "hit_count": 1,
                    "total_chunks": cr.get("total_chunks", 1),
                    "score_sum": cr["score"],
                }
            else:
                pd = page_data[path]
                pd["hit_count"] += 1
                pd["max_score"] = max(pd["max_score"], cr["score"])
                pd["score_sum"] += cr["score"]

            # 记录 chunk 定位信息（用于 match_positions）
            if cr.get("heading"):
                path_match_positions[path].append({
                    "heading": cr.get("heading", ""),
                    "breadcrumb": cr.get("breadcrumb", ""),
                    "score": cr["score"],
                })

        # 计算聚合 score 并排序
        results: list[dict] = []
        for path, pd in page_data.items():
            hit_ratio = pd["hit_count"] / max(pd["total_chunks"], 1)
            bonus = 0.15 * hit_ratio
            agg_score = pd["max_score"] + bonus

            # 取 top-3 match positions
            positions = sorted(
                path_match_positions.get(path, []),
                key=lambda x: x["score"],
                reverse=True,
            )[:3]

            results.append({
                "path": path,
                "score": round(min(agg_score, 1.0), 4),
                "raw_score": round(pd["max_score"], 4),
                "chunk_hits": pd["hit_count"],
                "search_method": "vector_chunk",
                "match_positions": positions,
            })

        # 按 score 降序，取 top-k
        results.sort(key=lambda r: r["score"], reverse=True)
        results = results[:k]
        results = _normalize_scores(results)

        return results

    def _search_hybrid(self, query: str, k: int = 10) -> list[dict]:
        """RRF 融合搜索（始终在 page 级融合）

        语义搜索不可用时自动降级为纯 BM25（不返回空结果、不伪标 hybrid）。
        """
        try:
            from src.core.embedding import get_embedding_engine

            engine = get_embedding_engine()
        except Exception:
            engine = None
        if engine is None or not engine.enabled:
            logger.warning("语义搜索不可用，混合搜索降级为关键词搜索 | query=%s", query)
            results, _ = self._search_bm25(query, k=k)
            for r in results:
                r["search_method"] = "bm25"
            return results

        bm25_results, _ = self._search_bm25(query, k=k * 2)
        vector_results = self._search_vector(query, k=k * 2)
        results = rrf_fuse(bm25_results, vector_results, top_n=k)
        for r in results:
            r["search_method"] = "hybrid"
            if "rrf_score" not in r:
                r["rrf_score"] = r.get("score", 0)
        results = _normalize_rrf_scores(results)
        return results

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _collect_pages(self, wiki_dir: str) -> list[dict]:
        """收集所有 wiki 页面的标题和内容"""
        if not os.path.isdir(wiki_dir):
            return []

        from src.db.repository import WikiRepository

        repo = WikiRepository()
        pages = []

        for root, _dirs, files in os.walk(wiki_dir):
            for f in files:
                if not f.endswith(".md"):
                    continue
                rel = os.path.relpath(os.path.join(root, f), wiki_dir).replace("\\", "/")
                meta = repo.get_page(rel)
                if meta is None:
                    continue

                content = ""
                try:
                    with open(os.path.join(root, f), "r", encoding="utf-8") as fh:
                        content = fh.read()
                except OSError:
                    continue

                pages.append({
                    "path": rel,
                    "title": meta.get("title", ""),
                    "content": content,
                })

        return pages


# ====================================================================
# 分数归一化
# ====================================================================

_EPSILON = 1e-8


def _normalize_scores(results: list[dict]) -> list[dict]:
    """Min-max 归一化 scores 到 [0, 1]，原值存入 raw_score"""
    if not results:
        return results

    scores = [r.get("score", 0) for r in results]
    min_s = min(scores)
    max_s = max(scores)

    for r in results:
        r["raw_score"] = r.get("score", 0)
        if max_s - min_s < _EPSILON:
            r["score"] = 0.0
        else:
            r["score"] = round((r["score"] - min_s) / (max_s - min_s), 4)
    return results


def _normalize_rrf_scores(results: list[dict]) -> list[dict]:
    """对 hybrid 结果，用 rrf_score 归一化作为主 score"""
    if not results:
        return results

    scores = [r.get("rrf_score", 0) for r in results]
    min_s = min(scores)
    max_s = max(scores)

    for r in results:
        if "raw_score" not in r:
            r["raw_score"] = r.get("score", 0)
        if max_s - min_s < _EPSILON:
            r["score"] = 0.0
        else:
            r["score"] = round((r["rrf_score"] - min_s) / (max_s - min_s), 4)
        r["rrf_score"] = round(r.get("rrf_score", 0), 4)
    return results


# ====================================================================
# RRF 融合
# ====================================================================


def rrf_fuse(
    bm25_results: list[dict],
    vector_results: list[dict],
    k: int = 60,
    top_n: int = 10,
) -> list[dict]:
    """RRF（Reciprocal Rank Fusion）融合两个搜索结果的排序

    Args:
        bm25_results: BM25 返回的结果列表
        vector_results: 向量搜索返回的结果列表
        k: RRF 常数（默认 60）
        top_n: 返回 top-N

    Returns:
        融合排序后的结果列表
    """
    from collections import defaultdict

    scores: dict[str, float] = defaultdict(float)
    lookup: dict[str, dict] = {}

    for rank, r in enumerate(bm25_results):
        path = r.get("path", "")
        scores[path] += 1.0 / (k + rank + 1)
        lookup[path] = r

    for rank, r in enumerate(vector_results):
        path = r.get("path", "")
        scores[path] += 1.0 / (k + rank + 1)
        if path not in lookup:
            lookup[path] = r

    sorted_paths = sorted(scores, key=scores.get, reverse=True)[:top_n]
    result = []
    for path in sorted_paths:
        entry = dict(lookup[path])
        entry["rrf_score"] = round(scores[path], 4)
        result.append(entry)

    return result
