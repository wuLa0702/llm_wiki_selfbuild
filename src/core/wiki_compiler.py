"""
Wiki Compiler — Agent 主流程编排
协调 ReadTool / WriteTool / LLMAdapter / WikiRepository 完成 Ingest
"""
import json
import re

from src.core.logging_config import get_logger
from src.core.models import AnalysisOutput, IngestResponse
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

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _sanitize_path(path: str) -> str:
        """清理路径中的非法字符"""
        if "|" in path:
            path = path.split("|")[0]
        path = path.replace("\n", "").replace("\r", "").strip()
        return path

    @staticmethod
    def _parse_response(response: str) -> dict[str, str]:
        """解析 LLM 返回的 ---PAGE:...---END--- 格式"""
        pages: dict[str, str] = {}
        pattern = re.compile(
            r"---PAGE:(.+?)---\s*\n(.*?)\n?---END---",
            re.DOTALL,
        )
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
        """从 Markdown 中提取 [[...]] 链接目标路径"""
        pattern = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")
        return [m.strip() for m in pattern.findall(content)]

    @staticmethod
    def _extract_title(content: str) -> str:
        """提取一级标题"""
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped[2:].strip()
        return "Untitled"

    @staticmethod
    def _extract_tags(content: str) -> list[str]:
        """从 Markdown 提取标签 #tag"""
        pattern = re.compile(r"(?:^|\s)#([\w一-鿿]+)")
        return list(set(pattern.findall(content)))

    def _guess_type(self, path: str) -> str:
        """根据路径前缀推测页面类型"""
        for t in ("entity", "concept", "source", "query"):
            if path.startswith(t) or path.startswith(f"{t}s/"):
                return t
        return "entity"

    # ------------------------------------------------------------------
    # 读写 + 日志 — 共享逻辑
    # ------------------------------------------------------------------

    def _get_index_context(self) -> str:
        """读取现有 wiki/index.md 作为上下文"""
        try:
            return self.reader.read_file("index.md")
        except FileNotFoundError:
            return "（空 — Wiki 中暂无页面）"

    def _write_pages(self, pages: dict[str, str]) -> tuple[list[str], list[str]]:
        """将解析出的页面写入文件并记录到数据库，返回 (created, updated)"""
        created, updated = [], []
        for path, page_content in pages.items():
            existing = self.repo.get_page(path)
            if existing:
                updated.append(path)
            else:
                created.append(path)

            self.writer.write_page(path, page_content)
            title = self._extract_title(page_content)
            tags = self._extract_tags(page_content)

            self.repo.add_page(
                path=path,
                title=title,
                page_type=self._guess_type(path),
                tags=tags,
                word_count=len(page_content),
            )
            for target in self._extract_links(page_content):
                self.repo.add_link(path, target)
        return created, updated

    def _update_log(self, source_path: str, pages: dict[str, str]) -> None:
        """更新 wiki/log.md"""
        paths = "\n".join(f"- [[{p}]]" for p in pages)
        entry = (
            f"## {self._now()}\n\n"
            f"**Ingested:** `raw/sources/{source_path}`\n"
            f"**Pages:**\n{paths}\n\n"
        )
        try:
            existing = self.reader.read_file("log.md")
        except FileNotFoundError:
            existing = "# Wiki 操作日志\n\n"
        self.writer.write_page("log.md", entry + existing if existing.strip() else entry)

    @staticmethod
    def _now() -> str:
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    # ------------------------------------------------------------------
    # Phase 2 — 两步 CoT
    # ------------------------------------------------------------------

    def ingest(self, source_path: str) -> dict:
        """
        两步 CoT：先分析再生成，带重试和降级

        容错策略：
          - Step 1 LLMError（瞬时故障）→ 重试 1 次 → 仍失败 → 降级 simple
          - Step 1 JSON 格式错误 → 直接降级 simple（重试无用）
          - Step 2 LLMError（瞬时故障）→ 重试 1 次 → 仍失败 → 抛出
          - Step 2 空输出 → 直接降级 simple（同 prompt 不会改变结果）
        """
        # 1. 读取源文件
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

        index_context = self._get_index_context()

        # 2. Step 1 — 分析（chat_structured 保证 JSON 输出）
        step1_prompt = (
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
                # JSON 格式错误 → 不重试，直接降级
                if "Failed to parse" in str(e):
                    logger.warning(
                        "Step 1 JSON 格式错误，降级单步 | source=%s error=%s",
                        source_path, e,
                    )
                    return self.ingest_simple(source_path)
                # API 瞬时故障 → 重试
                if attempt == 0:
                    logger.warning(
                        "Step 1 瞬时故障，重试 | attempt=1 source=%s error=%s",
                        source_path, e,
                    )
                    continue
                logger.warning(
                    "Step 1 重试后仍失败，降级单步 | source=%s error=%s",
                    source_path, e,
                )
                return self.ingest_simple(source_path)

        # 3. Step 2 — 生成（LLMError 重试，空输出降级）
        logger.info("两步 CoT Step 2 开始 | concepts=%d entities=%d",
                     len(analysis.get("concepts", [])),
                     len(analysis.get("entities", [])))

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
                    logger.warning(
                        "Step 2 瞬时故障，重试 | attempt=1 source=%s error=%s",
                        source_path, e,
                    )
                    continue
                logger.error(
                    "Step 2 重试后仍失败 | source=%s error=%s",
                    source_path, e,
                )
                raise

        # 4. 解析 & 写入
        pages = self._parse_response(raw_pages)
        if not pages:
            logger.warning("Step 2 无有效页面输出，降级单步 | source=%s", source_path)
            return self.ingest_simple(source_path)

        created, updated = self._write_pages(pages)
        self._update_log(source_path, pages)

        logger.info("两步 CoT 完成 | created=%d updated=%d", len(created), len(updated))
        return IngestResponse(
            status="success",
            pages_created=created,
            pages_updated=updated,
            message=f"Ingested '{source_path}': "
            f"{len(created)} created, {len(updated)} updated.",
        ).model_dump()

    @staticmethod
    def _parse_analysis_json(raw: str) -> dict:
        """
        解析 Step 1 的 JSON 输出

        尝试直接解析，失败时尝试提取 markdown 代码块中的 JSON
        """
        raw = raw.strip()

        # 直接解析
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 代码块
        match = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        raise json.JSONDecodeError("无法解析 JSON", raw, 0)

    # ------------------------------------------------------------------
    # Phase 1 遗留 — 单步模式（降级兼容）
    # ------------------------------------------------------------------

    def ingest_simple(self, source_path: str) -> dict:
        """单步 ingest（Phase 1 模式，作为 CoT 降级方案）"""
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

        created, updated = self._write_pages(pages)
        self._update_log(source_path, pages)

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
