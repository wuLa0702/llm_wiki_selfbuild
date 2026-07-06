"""
Wiki Compiler — Agent 主流程编排
协调 ReadTool / WriteTool / LLMAdapter / WikiRepository 完成 Ingest
"""
import json
import os
import re
from datetime import datetime

from src.core.cache import IngestCache
from src.core.logging_config import get_logger
from src.core.models import AnalysisOutput, IngestResponse
from src.core.privacy import PrivacyManager
from src.db.repository import WikiRepository
from src.llm.adapter import LLMAdapter, LLMError
from src.llm.prompts import (
    SYSTEM_PROMPT_INGEST,
    SYSTEM_PROMPT_INGEST_ANALYZE,
    INGEST_GENERATE_TEMPLATE,
)
from src.tools.read_tool import ReadTool
from src.tools.write_tool import WriteTool

logger = get_logger("compiler")


class CompilerError(Exception):
    """Wiki Compiler 基础异常"""


class WikiCompiler:
    """Agent 主流程：协调工具和 LLM 完成 Ingest/Query/Lint 操作"""

    def __init__(self) -> None:
        self.reader = ReadTool("raw")
        self.writer = WriteTool("wiki")
        self.llm = LLMAdapter()
        self.repo = WikiRepository()
        self.cache = IngestCache()
        self.privacy = PrivacyManager()

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
        try:
            return self._read_wiki_file("index.md")
        except FileNotFoundError:
            return "（空 — Wiki 中暂无页面）"

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
            overview = self.llm.chat(prompt=prompt, system_prompt=overview_prompt)
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

    # ==================================================================
    # Phase 2 — 两步 CoT
    # ==================================================================

    def ingest(self, source_path: str) -> dict:
        """两步 CoT：先分析再生成，带重试和降级"""
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

        # 0.5 隐私检测
        privacy_matches = self.privacy.match(content)
        if privacy_matches:
            logger.info(
                "隐私规则命中 | source=%s matches=%s",
                source_path, [m["keyword"] for m in privacy_matches],
            )

        index_context = self._get_index_context()
        purpose_context = self._get_purpose_context()

        # Step 1 — 分析（注入 purpose.md 让 LLM 了解知识库方向）
        purpose_section = f"知识库目标：\n{purpose_context}\n\n" if purpose_context else ""
        step1_prompt = (
            f"{purpose_section}"
            f"现有 Wiki 索引:\n\n{index_context}\n\n"
            f"请分析以下源文件内容:\n\n{content}"
        )
        for attempt in range(2):
            try:
                analysis = self.llm.chat_structured(
                    prompt=step1_prompt,
                    system_prompt=SYSTEM_PROMPT_INGEST_ANALYZE,
                    output_schema=AnalysisOutput,
                )
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
        self._update_nav_files(source_path, pages)
        self.cache.mark_ingested(source_path)

        logger.info("两步 CoT 完成 | created=%d updated=%d", len(created), len(updated))
        return IngestResponse(
            status="success",
            pages_created=created,
            pages_updated=updated,
            message=f"Ingested '{source_path}': "
            f"{len(created)} created, {len(updated)} updated.",
            confidence_summary=confidence_summary,
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

    def ingest_simple(self, source_path: str, privacy_matches: list[dict] | None = None) -> dict:
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

        if privacy_matches is None:
            privacy_matches = self.privacy.match(content)

        response = self.llm.chat(
            prompt=f"请处理以下源文件内容：\n\n{content}",
            system_prompt=SYSTEM_PROMPT_INGEST,
        )

        pages = self._parse_response(response)
        if not pages:
            return IngestResponse(
                status="success",
                message=f"No entities/concepts were extracted from '{source_path}'.",
            ).model_dump()

        created, updated = self._write_pages(pages, privacy_matches)
        self._update_nav_files(source_path, pages)
        self.cache.mark_ingested(source_path)

        return IngestResponse(
            status="success",
            pages_created=created,
            pages_updated=updated,
            message=f"Ingested '{source_path}': "
            f"{len(created)} created, {len(updated)} updated.",
        ).model_dump()

    # ------------------------------------------------------------------
    # Query / Lint — Phase 2
    # ------------------------------------------------------------------

    def query(self, question: str) -> dict:
        raise NotImplementedError("Phase 2 实现")

    def lint(self) -> dict:
        raise NotImplementedError("Phase 2 实现")
