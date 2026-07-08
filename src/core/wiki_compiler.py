"""
Wiki Compiler — Agent 主流程编排
协调 ReadTool / WriteTool / LLMAdapter / WikiRepository 完成 Ingest
"""
import json
import os
import re
from datetime import datetime

from src.core.cache import IngestCache
from src.core.graph import WikiGraph
from src.core.linter import LintTool
from src.core.logging_config import get_logger
from src.core.models import AnalysisOutput, IngestResponse
from src.core.privacy import PrivacyManager
from src.core.query_engine import QueryEngine
from src.core.task_queue import TaskQueue
from src.core.token_tracker import TokenTracker
from src.db.repository import WikiRepository
from src.llm.adapter import LLMAdapter, LLMError
from src.llm.prompts import (
    SYSTEM_PROMPT_INGEST,
    SYSTEM_PROMPT_INGEST_ANALYZE,
    INGEST_GENERATE_TEMPLATE,
)
from src.tools.read_tool import ReadTool
from src.tools.search_tool import SearchTool
from src.tools.write_tool import WriteTool

logger = get_logger("compiler")


class CompilerError(Exception):
    """Wiki Compiler 基础异常"""


class WikiCompiler:
    """Agent 主流程：协调工具和 LLM 完成 Ingest/Query/Lint 操作"""

    def __init__(self, task_queue: TaskQueue | None = None) -> None:
        self.reader = ReadTool("raw")
        self.writer = WriteTool("wiki")
        self.token_tracker = TokenTracker()
        self.llm = LLMAdapter(token_tracker=self.token_tracker)
        self.repo = WikiRepository()
        self.cache = IngestCache()
        self.privacy = PrivacyManager()
        self.graph = WikiGraph()
        self.search_tool = SearchTool()
        self.task_queue = task_queue
        self.query_engine = QueryEngine(
            repo=self.repo,
            search_tool=self.search_tool,
            graph=self.graph,
            llm=self.llm,
            writer=self.writer,
            token_tracker=self.token_tracker,
        )

    # ------------------------------------------------------------------
    # 内部工具 — 静态方法
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_path(path: str) -> str:
        if "|" in path:
            path = path.split("|")[0]
        path = path.replace("\n", "").replace("\r", "").strip()
        return path

    @staticmethod
    def _parse_response(response: str) -> dict[str, str]:
        pages: dict[str, str] = {}
        pattern = re.compile(r"---PAGE:(.+?)---\s*\n(.*?)\n?---END---", re.DOTALL)
        for match in pattern.finditer(response):
            path = WikiCompiler._sanitize_path(match.group(1))
            content = match.group(2).strip()
            if not path or "/" not in path or len(path) > 120:
                continue
            if content:
                pages[path] = content
        return pages

    @staticmethod
    def _extract_links(content: str) -> list[str]:
        pattern = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")
        return [m.strip() for m in pattern.findall(content)]

    @staticmethod
    def _extract_title(content: str) -> str:
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped[2:].strip()
        return "Untitled"

    @staticmethod
    def _extract_tags(content: str) -> list[str]:
        pattern = re.compile(r"(?:^|\s)#([\w一-鿿]+)")
        return list(set(pattern.findall(content)))

    @staticmethod
    def _extract_confidence_summary(pages: dict[str, str]) -> dict[str, int]:
        """从页面 frontmatter 提取置信度统计"""
        summary: dict[str, int] = {"high": 0, "medium": 0, "low": 0}
        for c in pages.values():
            m = re.search(r"confidence:\s*(\w+)", c)
            if m:
                level = m.group(1).lower()
                if level in summary:
                    summary[level] += 1
        return {k: v for k, v in summary.items() if v > 0}

    def _guess_type(self, path: str) -> str:
        for t in ("entity", "concept", "source", "query"):
            if path.startswith(t) or path.startswith(f"{t}s/"):
                return t
        return "entity"

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    @staticmethod
    def _today() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    # ------------------------------------------------------------------
    # 读写页面的共享逻辑
    # ------------------------------------------------------------------

    def _read_wiki_file(self, path: str) -> str:
        """读取 wiki/ 下的文件（绕过 ReadTool 的 raw/ 限制）"""
        full = os.path.join(self.writer.base_dir, path)
        if not os.path.isfile(full):
            raise FileNotFoundError(f"Wiki file not found: {path}")
        with open(full, "r", encoding="utf-8") as f:
            return f.read()

    def _get_index_context(self) -> str:
        """返回完整 index.md 内容（已废弃，保留兼容，请使用 _index_summary）"""
        try:
            return self._read_wiki_file("index.md")
        except FileNotFoundError:
            return "（空 — Wiki 中暂无页面）"

    def _index_summary(self) -> str:
        """
        返回 index 的数据库摘要（~500 tokens），替代完整 index.md

        从 SQLite 读取统计和最近更新，比读 index.md 省 ~80% tokens。
        用于 ingest Step 1 的 LLM 上下文。

        Returns:
            摘要文本，如 "Wiki 总页面数：15\n按类型分布：..."
        """
        import sqlite3

        conn = sqlite3.connect(self.repo.db_path)
        conn.row_factory = sqlite3.Row

        total = conn.execute(
            "SELECT COUNT(*) as n FROM wiki_pages"
        ).fetchone()["n"]

        by_type = conn.execute(
            "SELECT page_type, COUNT(*) as n FROM wiki_pages GROUP BY page_type"
        ).fetchall()

        recent = conn.execute(
            "SELECT path, title FROM wiki_pages ORDER BY updated_at DESC LIMIT 10"
        ).fetchall()

        conn.close()

        type_dist = "，".join(
            f"{r['page_type']}: {r['n']}" for r in by_type
        ) if by_type else "暂无"

        lines = [
            f"Wiki 总页面数：{total}",
            f"按类型分布：{type_dist}",
            "最近更新的页面：",
        ]
        for r in recent:
            lines.append(f"  - {r['path']} — {r['title']}")

        return "\n".join(lines)

    def _get_purpose_context(self) -> str:
        """读取 purpose.md 作为知识库方向上下文"""
        import os as _os
        purpose_path = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "purpose.md")
        if not _os.path.isfile(purpose_path):
            return ""
        try:
            with open(purpose_path, "r", encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    @staticmethod
    def _inject_privacy_frontmatter(content: str, matches: list[dict]) -> str:
        """在 YAML frontmatter 中注入 visibility: restricted + privacy_categories"""
        if not matches:
            return content
        categories = sorted(set(m["category"] for m in matches))

        lines = content.split("\n")
        if len(lines) >= 2 and lines[0].strip() == "---":
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    lines.insert(i, f"privacy_categories: {categories}")
                    lines.insert(i, f"visibility: restricted")
                    break
        return "\n".join(lines)

    def _write_pages(self, pages: dict[str, str], privacy_matches: list[dict] | None = None) -> tuple[list[str], list[str]]:
        created, updated = [], []
        for path, page_content in pages.items():
            if privacy_matches:
                page_content = self._inject_privacy_frontmatter(page_content, privacy_matches)
            existing = self.repo.get_page(path)
            if existing:
                updated.append(path)
            else:
                created.append(path)
            self.writer.write_page(path, page_content)
            self.repo.add_page(
                path=path,
                title=self._extract_title(page_content),
                page_type=self._guess_type(path),
                tags=self._extract_tags(page_content),
                word_count=len(page_content),
            )
            for target in self._extract_links(page_content):
                self.repo.add_link(path, target)
        return created, updated

    # ==================================================================
    # Phase 2 第三步：导航文件自动维护
    # ==================================================================

    def _update_index(self) -> None:
        """3.1 自动更新 wiki/index.md — 全局索引 + 目录"""
        import sqlite3

        conn = sqlite3.connect(self.repo.db_path)
        conn.row_factory = sqlite3.Row

        # 按类型统计
        stats = conn.execute(
            "SELECT page_type, COUNT(*) as n FROM wiki_pages GROUP BY page_type"
        ).fetchall()

        # 最近更新
        recent = conn.execute(
            "SELECT path, title, updated_at FROM wiki_pages "
            "ORDER BY updated_at DESC LIMIT 20"
        ).fetchall()

        # 各类型页面列表
        type_names = {"entity": "实体", "concept": "概念", "source": "来源", "query": "问答"}
        catalog_sections = []
        for ptype, label in type_names.items():
            rows = conn.execute(
                "SELECT path, title FROM wiki_pages WHERE page_type = ? ORDER BY path",
                (ptype,),
            ).fetchall()
            if rows:
                items = "\n".join(f"- [[{r['path']}]] — {r['title']}" for r in rows)
                catalog_sections.append(f"## {label}目录 ({len(rows)})\n\n{items}")

        conn.close()

        # 统计区域
        total = sum(s["n"] for s in stats)
        stat_lines = [f"- {type_names.get(s['page_type'], s['page_type'])}数：{s['n']}" for s in stats]
        stat_lines.append(f"- 页面总数：{total}")
        stat_lines.append(f"- 最后更新：{self._now()}")

        # 最近更新
        recent_lines = []
        for r in recent:
            date = r["updated_at"][:10] if r["updated_at"] else "?"
            recent_lines.append(f"- [[{r['path']}]] — {r['title']} ({date})")

        index = f"""# Wiki 全局索引

> 自动维护 — 每次 Ingest 后由 `_update_index()` 生成

## 统计

{chr(10).join(stat_lines)}

## 最近更新

{chr(10).join(recent_lines) if recent_lines else '（暂无页面）'}

{chr(10).join(catalog_sections) if catalog_sections else '（暂无页面）'}
"""
        self.writer.write_page("index.md", index, validate=False)

    def _update_overview(self) -> None:
        """3.2 调用 LLM 生成 wiki/overview.md — 全局综述"""
        # 读取 index.md 作为输入
        try:
            index_content = self._read_wiki_file("index.md")
        except FileNotFoundError:
            return  # index 还没生成，跳过

        prompt = (
            "以下是 Wiki 知识库的索引页面。请综合所有信息，"
            "生成一份全局综述，包括：\n"
            "1. 主题分布（哪些领域内容最丰富）\n"
            "2. 核心实体和概念的关联网络\n"
            "3. 知识缺口（哪些主题缺乏内容）\n"
            "4. 推荐后续摄入的方向\n\n"
            f"{index_content}"
        )

        overview_prompt = (
            "你是一个知识库分析员。请简洁地综合 Wiki 索引，"
            "写一份约 300 字的全局综述。用中文。"
        )

        try:
            overview = self.llm.chat(prompt=prompt, system_prompt=overview_prompt, operation="overview")
        except LLMError:
            overview = "_（LLM 生成综述失败，下次 ingest 时重试）_"

        self.writer.write_page(
            "overview.md",
            f"# Wiki 全局综述\n\n> 自动生成 — {self._now()}\n\n{overview}\n",
            validate=False,
        )

    def _update_log(self, source_path: str, pages: dict[str, str]) -> None:
        """3.3 修正 wiki/log.md 格式 — 标题在顶部，新条目插在标题后"""
        paths = "\n".join(f"- [[{p}]]" for p in pages)
        entry = (
            f"## [{self._today()}] ingest | {source_path}\n\n"
            f"**Source:** `raw/sources/{source_path}`\n"
            f"**Pages created/updated:** {', '.join(pages.keys())}\n"
            f"**Conflicts:** 无\n\n"
        )

        title_line = "# Wiki 操作日志\n\n"
        try:
            existing = self._read_wiki_file("log.md")
            if existing.startswith(title_line):
                existing = existing[len(title_line):]
        except FileNotFoundError:
            existing = ""

        self.writer.write_page("log.md", title_line + entry + existing, validate=False)

    def _update_nav_files(self, source_path: str, pages: dict[str, str]) -> None:
        """第三步统一入口：更新所有导航文件"""
        self._update_log(source_path, pages)
        self._update_index()
        self._update_overview()

    @staticmethod
    def _build_token_usage(
        s1: dict | None, s2: dict | None, ov: dict | None
    ) -> dict | None:
        """
        组装 token_usage 摘要字典

        Args:
            s1: Step 1 的 last_usage（chat_structured）
            s2: Step 2 的 last_usage（chat_template）
            ov: overview 的 last_usage（chat）

        Returns:
            {"step1_input": N, "step1_output": N, "step2_input": N, ...} 或 None
        """
        usage: dict[str, int] = {}
        if s1:
            usage["step1_input"] = s1.get("input_tokens", 0)
            usage["step1_output"] = s1.get("output_tokens", 0)
        if s2:
            usage["step2_input"] = s2.get("input_tokens", 0)
            usage["step2_output"] = s2.get("output_tokens", 0)
        if ov and ov != s2:
            usage["overview_input"] = ov.get("input_tokens", 0)
            usage["overview_output"] = ov.get("output_tokens", 0)

        if not usage:
            return None

        usage["total"] = sum(v for v in usage.values())
        return usage

    # ==================================================================
    # Phase 2 — 两步 CoT
    # ==================================================================

    def ingest(self, source_path: str, max_source_chars: int | None = None) -> dict:
        """两步 CoT：先分析再生成，带重试和降级

        Args:
            source_path: 源文件路径（相对于 raw/sources/）
            max_source_chars: 源文件最大字符数，超出则截断。
                              默认从环境变量 DEBUG_MAX_CHARS 读取（0=不限制）。
        """
        # 0. 增量缓存 — 内容未变则跳过
        if not self.cache.has_changed(source_path):
            logger.info("缓存命中，跳过 ingest | source=%s", source_path)
            return IngestResponse(
                status="skipped",
                message=f"Source unchanged: '{source_path}'.",
            ).model_dump()

        try:
            content = self.reader.read_file(f"sources/{source_path}")
        except FileNotFoundError:
            raise CompilerError(f"Source file not found: raw/sources/{source_path}")
        except PermissionError as e:
            raise CompilerError(f"Access denied: {e}")

        if not content.strip():
            return IngestResponse(
                status="success",
                message=f"Source file '{source_path}' is empty, nothing to ingest.",
            ).model_dump()

        if max_source_chars is None:
            raw = os.environ.get("DEBUG_MAX_CHARS", "0")
            max_source_chars = int(raw) if raw.isdigit() else 0

        if max_source_chars > 0 and len(content) > max_source_chars:
            logger.info(
                "源文件过长，截断 | source=%s %d→%d chars",
                source_path, len(content), max_source_chars,
            )
            content = content[:max_source_chars] + f"\n\n_（内容截断，仅前 {max_source_chars} 字符）_"

        # 0.5 隐私检测
        privacy_matches = self.privacy.match(content)
        if privacy_matches:
            logger.info(
                "隐私规则命中 | source=%s matches=%s",
                source_path, [m["keyword"] for m in privacy_matches],
            )

        index_context = self._index_summary()
        purpose_context = self._get_purpose_context()

        # Step 1 — 分析（注入 purpose.md 让 LLM 了解知识库方向）
        purpose_section = f"知识库目标：\n{purpose_context}\n\n" if purpose_context else ""
        step1_prompt = (
            f"{purpose_section}"
            f"现有 Wiki 索引:\n\n{index_context}\n\n"
            f"请分析以下源文件内容:\n\n{content}"
        )
        s1 = None
        for attempt in range(2):
            try:
                analysis = self.llm.chat_structured(
                    prompt=step1_prompt,
                    system_prompt=SYSTEM_PROMPT_INGEST_ANALYZE,
                    output_schema=AnalysisOutput,
                    operation="ingest_step1",
                )
                s1 = self.llm.last_usage  # 捕获 Step 1 token 用量
                break
            except LLMError as e:
                if "Failed to parse" in str(e):
                    logger.warning("Step 1 JSON 格式错误，降级单步 | %s", e)
                    return self.ingest_simple(source_path)
                if attempt == 0:
                    logger.warning("Step 1 瞬时故障，重试 | attempt=1 source=%s", source_path)
                    continue
                logger.warning("Step 1 重试后仍失败，降级单步 | %s", e)
                return self.ingest_simple(source_path)

        # Step 2 — 生成
        logger.info("两步 CoT Step 2 开始 | concepts=%d entities=%d",
                     len(analysis.get("concepts", [])), len(analysis.get("entities", [])))

        analysis_str = json.dumps(analysis, ensure_ascii=False)
        for attempt in range(2):
            try:
                raw_pages = self.llm.chat_template(
                    INGEST_GENERATE_TEMPLATE,
                    operation="ingest_step2",
                    source_name=f"raw/sources/{source_path}",
                    analysis_json=analysis_str,
                )
                break
            except LLMError as e:
                if attempt == 0:
                    logger.warning("Step 2 瞬时故障，重试 | attempt=1 source=%s", source_path)
                    continue
                logger.error("Step 2 重试后仍失败 | %s", e)
                raise

        pages = self._parse_response(raw_pages)
        if not pages:
            logger.warning("Step 2 无有效页面输出，降级单步 | source=%s", source_path)
            return self.ingest_simple(source_path, privacy_matches)

        confidence_summary = self._extract_confidence_summary(pages)
        created, updated = self._write_pages(pages, privacy_matches)

        # 捕获 Step 2 的 token 用量
        s2 = self.llm.last_usage

        self._update_nav_files(source_path, pages)
        self.cache.mark_ingested(source_path)
        # 图谱重建交给后台任务，不阻塞 ingest 返回
        self.graph.invalidate()
        if self.task_queue:
            self.task_queue.enqueue("rebuild_graph")

        # 捕获 overview 的 token 用量（如果调了 LLM）
        ov = self.llm.last_usage if self.llm.last_usage != s2 else None

        # 组装 token_usage 摘要
        token_usage = self._build_token_usage(s1, s2, ov)

        logger.info("两步 CoT 完成 | created=%d updated=%d", len(created), len(updated))
        return IngestResponse(
            status="success",
            pages_created=created,
            pages_updated=updated,
            message=f"Ingested '{source_path}': "
            f"{len(created)} created, {len(updated)} updated.",
            confidence_summary=confidence_summary,
            token_usage=token_usage,
        ).model_dump()

    @staticmethod
    def _parse_analysis_json(raw: str) -> dict:
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise json.JSONDecodeError("无法解析 JSON", raw, 0)

    # ==================================================================
    # Phase 1 遗留 — 单步模式（降级兼容）
    # ==================================================================

    def ingest_simple(self, source_path: str, privacy_matches: list[dict] | None = None,
                       max_source_chars: int | None = None) -> dict:
        # 4. 缓存检查
        if not self.cache.has_changed(source_path):
            logger.info("缓存命中，跳过 simple ingest | source=%s", source_path)
            return IngestResponse(
                status="skipped",
                message=f"Source unchanged: '{source_path}'.",
            ).model_dump()

        try:
            content = self.reader.read_file(f"sources/{source_path}")
        except FileNotFoundError:
            raise CompilerError(f"Source file not found: raw/sources/{source_path}")
        except PermissionError as e:
            raise CompilerError(f"Access denied: {e}")

        if not content.strip():
            return IngestResponse(
                status="success",
                message=f"Source file '{source_path}' is empty, nothing to ingest.",
            ).model_dump()

        # 截断
        if max_source_chars is None:
            raw = os.environ.get("DEBUG_MAX_CHARS", "0")
            max_source_chars = int(raw) if raw.isdigit() else 0
        if max_source_chars > 0 and len(content) > max_source_chars:
            logger.info("源文件过长，截断 (simple) | %d→%d", len(content), max_source_chars)
            content = content[:max_source_chars] + f"\n\n_（内容截断，仅前 {max_source_chars} 字符）_"

        if privacy_matches is None:
            privacy_matches = self.privacy.match(content)

        response = self.llm.chat(
            prompt=f"请处理以下源文件内容：\n\n{content}",
            system_prompt=SYSTEM_PROMPT_INGEST,
            operation="ingest_simple",
        )

        pages = self._parse_response(response)
        if not pages:
            return IngestResponse(
                status="success",
                message=f"No entities/concepts were extracted from '{source_path}'.",
            ).model_dump()

        s1 = self.llm.last_usage  # 单步的模式，算作 step1
        created, updated = self._write_pages(pages, privacy_matches)
        self._update_nav_files(source_path, pages)
        ov = self.llm.last_usage if self.llm.last_usage != s1 else None

        self.cache.mark_ingested(source_path)
        self.graph.invalidate()
        if self.task_queue:
            self.task_queue.enqueue("rebuild_graph")
        token_usage = self._build_token_usage(s1, None, ov)

        return IngestResponse(
            status="success",
            pages_created=created,
            pages_updated=updated,
            message=f"Ingested '{source_path}': "
            f"{len(created)} created, {len(updated)} updated.",
            token_usage=token_usage,
        ).model_dump()

    # ------------------------------------------------------------------
    # Query — Phase 3 Step 4
    # ------------------------------------------------------------------

    def query(self, question: str, max_pages: int = 10, archive: bool = False) -> dict:
        """基于 wikilinks 图扩展的 Wiki 导航查询

        Args:
            question: 用户问题
            max_pages: 最多加载的候选页面数
            archive: 是否将答案归档到 wiki/queries/

        Returns:
            {"answer": "...", "sources": [...], "confidence": "...", "archived": ...}
        """
        result = self.query_engine.query(
            question, max_pages=max_pages, archive=archive
        )
        # 归档后更新 index + 标记图脏（懒重建）
        if result.get("archived"):
            self._update_index()
            self.graph.invalidate()
        return result

    # ------------------------------------------------------------------
    # Lint — Phase 3 Step 5
    # ------------------------------------------------------------------

    def lint(self, semantic: bool = False) -> dict:
        """运行 Lint 检查

        Args:
            semantic: 是否启用 LLM 语义检测（默认 False，走静态检查）

        Returns:
            静态或语义检测结果
        """
        linter = LintTool(wiki_dir=self.writer.base_dir)
        if semantic:
            return linter.check_semantic(llm=self.llm, repo=self.repo)
        return linter.run_all()
