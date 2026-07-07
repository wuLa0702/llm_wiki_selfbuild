"""
Query 查询引擎 — 基于 wikilinks 图扩展的导航式查询（非 RAG）

核心设计：不靠向量相似度检索 chunk，而是通过 wikilinks 图扩展
发现"不包含关键词但被关联页面指向"的候选页。

流程：
  1. 定位候选页（SQLite → 全文搜索 → 图扩展 → LLM 兜底）
  2. 读取 + 排序上下文
  3. LLM 综合回答
  4. 可选：归档到 wiki/queries/
"""
import os
import re
from datetime import datetime

from pydantic import BaseModel

from src.core.logging_config import get_logger

logger = get_logger("query")


class QueryOutput(BaseModel):
    """LLM 回答的结构化输出"""
    answer: str
    confidence: str  # high / medium / low
    gaps: list[str] = []


class QueryEngine:
    """Wiki 查询引擎 — 候选定位 + 图扩展 + LLM 合成"""

    def __init__(
        self,
        repo,
        search_tool,
        graph,
        llm,
        writer,
        token_tracker=None,
    ) -> None:
        """
        Args:
            repo: WikiRepository 实例
            search_tool: SearchTool 实例
            graph: WikiGraph 实例
            llm: LLMAdapter 实例
            writer: WriteTool 实例
            token_tracker: TokenTracker 实例（可选）
        """
        self.repo = repo
        self.search_tool = search_tool
        self.graph = graph
        self.llm = llm
        self.writer = writer
        self.token_tracker = token_tracker

    # ==================================================================
    # 公开方法
    # ==================================================================

    def query(self, question: str, max_pages: int = 10, archive: bool = False) -> dict:
        """
        基于页面导航的 Wiki 查询

        Args:
            question: 用户问题
            max_pages: 最多加载的候选页面数
            archive: 是否将答案归档到 wiki/queries/

        Returns:
            {
                "answer": "综合回答（Markdown，含 [[wikilinks]] 引用）",
                "sources": ["entities/xxx.md", ...],
                "confidence": "high / medium / low",
                "gaps": ["缺失信息点"],
                "archived": "queries/xxx.md" | None,
            }
        """
        # Step 1: 定位候选页面
        candidates = self._locate_candidates(question, max_pages)
        logger.info("Query 定位候选 | question=%s candidates=%d", question, len(candidates))

        if not candidates:
            return {
                "answer": "知识库中暂无相关内容，无法回答该问题。",
                "sources": [],
                "confidence": "low",
                "gaps": [f"知识库未覆盖：{question}"],
                "archived": None,
            }

        # Step 2: 构建上下文
        context = self._build_context(candidates)
        logger.info("Query 上下文构建完成 | pages=%d chars=%d", len(candidates), len(context))

        # Step 3: LLM 综合回答
        answer_data = self._synthesize_answer(question, context)
        answer_data["sources"] = candidates

        # Step 4: 可选归档
        archived = None
        if archive and answer_data.get("confidence") not in (None, "low"):
            archived = self._archive_query(question, answer_data)
        answer_data["archived"] = archived

        return answer_data

    # ==================================================================
    # Step 1 — 定位候选页面（三角定位）
    # ==================================================================

    def _locate_candidates(self, question: str, limit: int) -> list[str]:
        """
        混合策略定位候选页面：SQLite → 全文搜索 → 图扩展 → LLM 兜底

        Returns:
            去重后的候选页面路径列表（最多 limit 个）
        """
        paths: set[str] = set()

        # 策略 A: SQLite 搜索（标题/路径/标签匹配，最快）
        for page in self.repo.search_pages(question, limit=limit):
            paths.add(page["path"])

        # 策略 B: 全文关键词搜索（文件内容）
        for result in self.search_tool.search(question):
            paths.add(result["path"])

        # 策略 C: WikiGraph 图扩展
        # 对已找到的候选页，通过 wikilinks 图发现"不含关键词但被关联指向"的页面
        expanded: set[str] = set()
        for p in list(paths):
            expanded.update(self.graph.neighbors(p, depth=1))
        paths.update(expanded)

        # 策略 D: 如果候选太少（< 3），LLM 读 index.md 推荐
        if len(paths) < 3:
            llm_suggestions = self._llm_suggest_pages(question)
            paths.update(llm_suggestions)

        return list(paths)[:limit]

    def _llm_suggest_pages(self, question: str) -> list[str]:
        """LLM 读 index.md 推荐相关页面（兜底策略）"""
        try:
            index_content = self._read_wiki_file("index.md")
        except (FileNotFoundError, OSError):
            return []

        prompt = (
            f"用户问题：{question}\n\n"
            f"以下是 Wiki 知识库的索引，请从中选出最相关的页面路径\n"
            f"（每行一个，不要编号，不要多余文字）：\n\n{index_content}"
        )
        try:
            raw = self.llm.chat(prompt=prompt, system_prompt="你是一个知识库导航员。从索引中列出最相关的 3-5 个页面路径，每行一个。", operation="query_suggest_pages")
            paths = []
            for line in raw.strip().split("\n"):
                line = line.strip().strip("-*").strip()
                if line.endswith(".md") and "/" in line:
                    paths.append(line)
            logger.info("LLM 推荐页面 | paths=%s", paths)
            return paths
        except Exception as exc:
            logger.warning("LLM 推荐页面失败 | %s", exc)
            return []

    # ==================================================================
    # Step 2 — 读取 + 排序上下文
    # ==================================================================

    def _build_context(self, candidates: list[str]) -> str:
        """
        读取候选页面内容，组装为 LLM 上下文

        每个页面用 ---PAGE: <path> --- 分隔，保持格式一致方便 LLM 识别
        """
        sections: list[str] = []
        for path in candidates:
            try:
                content = self._read_wiki_file(path)
            except (FileNotFoundError, OSError):
                continue

            # 去掉 YAML frontmatter（减少 token 消耗）
            body = self._strip_frontmatter(content)
            # 截断过长的页面（取前 2000 字符）
            if len(body) > 2000:
                body = body[:2000] + "\n\n_（内容截断）_"
            sections.append(f"---PAGE: {path} ---\n{body}")

        if not sections:
            return "（知识库中暂无相关页面内容）"

        return "\n\n".join(sections)

    @staticmethod
    def _strip_frontmatter(content: str) -> str:
        """去除 YAML frontmatter，保留正文"""
        lines = content.split("\n")
        if len(lines) >= 2 and lines[0].strip() == "---":
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    return "\n".join(lines[i + 1:])
        return content

    # ==================================================================
    # Step 3 — LLM 综合回答
    # ==================================================================

    def _synthesize_answer(self, question: str, context: str) -> dict:
        """
        LLM 基于上下文综合回答

        Returns:
            {"answer": "...", "confidence": "...", "gaps": [...]}
        """
        from src.llm.prompts import SYSTEM_PROMPT_QUERY

        prompt = (
            f"## 用户问题\n\n{question}\n\n"
            f"## 相关页面内容\n\n{context}\n\n"
            "请基于以上 Wiki 页面内容回答用户问题。"
        )

        try:
            result = self.llm.chat_structured(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_QUERY,
                output_schema=QueryOutput,
                operation="query_synthesize",
            )
        except Exception as exc:
            logger.error("Query LLM 调用失败 | %s", exc)
            # 降级：返回基础回答
            return {
                "answer": f"（LLM 调用失败，无法合成回答）\n\n检索到 {context.count('---PAGE:')} 个相关页面，但 LLM 合成时出错。",
                "confidence": "low",
                "gaps": [f"LLM 错误：{exc}"],
            }

        return {
            "answer": result.get("answer", ""),
            "confidence": result.get("confidence", "low"),
            "gaps": result.get("gaps", []),
        }

    # ==================================================================
    # Step 4 — 答案归档
    # ==================================================================

    def _archive_query(self, question: str, answer_data: dict) -> str | None:
        """
        将查询结果归档到 wiki/queries/

        生成 slug 文件名，写入完整 Markdown 页面，更新元数据
        """
        answer = answer_data.get("answer", "")
        if not answer or not answer.strip():
            return None

        slug = self._question_to_slug(question)
        path = f"queries/{slug}.md"

        sources = answer_data.get("sources", [])
        sources_yaml = "\n".join(f"  - {s}" for s in sources)

        content = (
            f"---\n"
            f"title: \"{question}\"\n"
            f"type: query\n"
            f"created: {self._today()}\n"
            f"tags: [query]\n"
            f"confidence: {answer_data.get('confidence', 'medium')}\n"
            f"sources:\n{sources_yaml}\n"
            f"---\n\n"
            f"# {question}\n\n"
            f"{answer}\n\n"
            f"## 来源\n\n"
        )
        for s in sources:
            content += f"- [[{s}]]\n"

        try:
            self.writer.write_page(path, content)
            self.repo.add_page(
                path=path,
                title=question,
                page_type="query",
                tags=["query"],
                word_count=len(content),
            )
            logger.info("Query 答案归档 | path=%s", path)
            return path
        except Exception as exc:
            logger.warning("Query 答案归档失败 | path=%s error=%s", path, exc)
            return None

    @staticmethod
    def _question_to_slug(question: str) -> str:
        """
        从问题生成安全的文件名 slug（取前 30 个有效字符）

        保留中文、字母、数字，其余替换为连字符
        """
        # 取前 30 字符
        raw = question.strip()[:30]
        # 保留中文、字母、数字、空格
        cleaned = re.sub(r"[^\w一-鿿\s-]", "", raw)
        # 空格 → 连字符
        slug = re.sub(r"\s+", "-", cleaned.strip().lower())
        # 去掉首尾连字符
        slug = slug.strip("-")
        return slug if slug else "query"

    # ==================================================================
    # 内部工具
    # ==================================================================

    def _read_wiki_file(self, path: str) -> str:
        """读取 wiki/ 下的文件"""
        full = os.path.join(self.writer.base_dir, path)
        if not os.path.isfile(full):
            raise FileNotFoundError(f"Wiki file not found: {path}")
        with open(full, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _today() -> str:
        return datetime.now().strftime("%Y-%m-%d")
