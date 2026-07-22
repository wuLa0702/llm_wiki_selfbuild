"""
BM25 关键词搜索 — 标题加权 + Bigram 分词 + 章节级多命中

比 SQLite LIKE 更精确：词频（TF）x 逆文档频率（IDF）
比向量搜索更快：纯内存计算，零 API 调用

依赖：rank_bm25（纯 Python，零 C 扩展）
"""
import logging
import re

from rank_bm25 import BM25Okapi

from src.core.search.bigram import build_searchable_tokens, tokenize

logger = logging.getLogger("search.bm25")

# 章节标题匹配（## 或 ###）
SECTION_HEADER_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


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
        self._titles: list[str] = []        # 页面标题
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
        self._titles = []
        tokenized_corpus: list[list[str]] = []

        for p in pages:
            path = p.get("path", "")
            title = p.get("title", "")
            content = p.get("content", "")
            self._paths.append(path)
            self._titles.append(title)
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

    def search(self, query: str, k: int = 10) -> tuple[list[dict], int]:
        """BM25 搜索（含章节级多命中）

        Args:
            query: 搜索关键词
            k: 最大返回条数

        Returns:
            (results, total_matched)
            results: [{"path": "...", "score": 0.85, "title": "...", "snippet": "...",
                       "match_positions": [...]}, ...]
            total_matched: 所有匹配文档总数（用于翻页）
            索引为空或未构建时返回([], 0)。
        """
        if not self._index or self._dirty:
            return [], 0

        tokens = build_searchable_tokens(query)
        if not tokens:
            return [], 0

        scores = self._index.get_scores(tokens)
        total_matched = sum(1 for s in scores if s > 0)

        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:k]

        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                break  # 后面的分数只会更低或为零
            content = self._corpus[idx]
            match_positions = self._get_section_matches(content, tokens)

            results.append({
                "path": self._paths[idx],
                "title": self._titles[idx],
                "score": round(float(scores[idx]), 4),
                "snippet": content[:150].replace("\n", " "),
                "match_positions": match_positions,
            })

        return results, total_matched

    # ------------------------------------------------------------------
    # 章节级多命中
    # ------------------------------------------------------------------

    @staticmethod
    def _get_section_matches(content: str, query_tokens: list[str]) -> list[dict]:
        """按章节切分内容，找出匹配度高的章节

        Args:
            content: 页面 Markdown 全文
            query_tokens: 查询分词结果（已去停用词）

        Returns:
            最多 5 个匹配章节，按匹配分降序：
            [{"section": "标题", "snippet": "段落片段", "line": 行号, "score": 匹配分}, ...]
        """
        lines = content.split("\n")
        sections: list[dict] = []  # [{title, line, text, tokens}, ...]

        current_title = ""
        current_line = 1
        current_text: list[str] = []

        for i, line in enumerate(lines):
            m = SECTION_HEADER_RE.match(line)
            if m and current_text:
                # 保存上一个章节
                text = "\n".join(current_text).strip()
                if text:
                    sections.append({
                        "title": current_title,
                        "line": max(1, current_line - len(current_text) + 1),
                        "text": text,
                    })
                current_text = []
                current_line = i + 1
                current_title = m.group(2).strip()
            elif m:
                current_line = i + 1
                current_title = m.group(2).strip()
            else:
                current_text.append(line)

        # 最后一个章节
        text = "\n".join(current_text).strip()
        if text:
            sections.append({
                "title": current_title,
                "line": current_line,
                "text": text,
            })

        if not sections:
            return []

        # 对每个章节计算匹配分：多少查询 token 在该章节中出现
        for s in sections:
            section_tokens = set(tokenize(s["text"]))
            if not query_tokens:
                s["score"] = 0
                continue
            matched = sum(1 for t in query_tokens if t in section_tokens)
            s["score"] = round(matched / len(query_tokens), 4)

        # 按匹配分降序，取 top-5
        sections.sort(key=lambda s: s["score"], reverse=True)
        top = [s for s in sections if s["score"] > 0][:5]

        return [
            {
                "section": s["title"],
                "snippet": s["text"][:120].replace("\n", " "),
                "line": s["line"],
                "score": s["score"],
            }
            for s in top
        ]

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
        self._titles = []
        self._dirty = True
