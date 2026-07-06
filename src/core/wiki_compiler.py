"""
Wiki Compiler — Agent 主流程编排
协调 ReadTool / WriteTool / LLMAdapter / WikiRepository 完成 Ingest
"""
import re

from src.core.models import IngestResponse
from src.db.repository import WikiRepository
from src.llm.adapter import LLMAdapter
from src.llm.prompts import SYSTEM_PROMPT_INGEST
from src.tools.read_tool import ReadTool
from src.tools.write_tool import WriteTool


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
        # 去掉 LLM 可能误加的 | 显示名后缀
        if "|" in path:
            path = path.split("|")[0]
        # 去掉换行、回车等
        path = path.replace("\n", "").replace("\r", "").strip()
        return path

    @staticmethod
    def _parse_response(response: str) -> dict[str, str]:
        """
        解析 LLM 返回的页面内容

        LLM 输出格式:
            ---PAGE:entities/xxx.md---
            # Title
            content
            ---END---

        Args:
            response: LLM 的完整回复文本

        Returns:
            {path: markdown_content} 字典，可能为空
        """
        pages: dict[str, str] = {}
        pattern = re.compile(
            r"---PAGE:(.+?)---\s*\n(.*?)\n?---END---",
            re.DOTALL,
        )
        for match in pattern.finditer(response):
            path = WikiCompiler._sanitize_path(match.group(1))
            content = match.group(2).strip()
            # 拒绝明显非法的路径
            if not path or "/" not in path or len(path) > 120:
                continue
            if content:
                pages[path] = content
        return pages

    @staticmethod
    def _extract_links(content: str) -> list[str]:
        """从 Markdown 内容中提取 [[...]] 双向链接的目标路径"""
        pattern = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")
        return [m.strip() for m in pattern.findall(content)]

    @staticmethod
    def _extract_title(content: str) -> str:
        """从 Markdown 内容提取一级标题作为页面标题"""
        for line in content.split("\n"):
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                return stripped[2:].strip()
        return "Untitled"

    @staticmethod
    def _extract_tags(content: str) -> list[str]:
        """从 Markdown 内容中提取标签（如 #AI #编程）"""
        pattern = re.compile(r"(?:^|\s)#([\w一-鿿]+)")
        return list(set(pattern.findall(content)))

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------

    def ingest(self, source_path: str) -> dict:
        """
        Ingest 一个源文件到 Wiki 知识库

        流程:
          1. ReadTool 读取 raw/sources/<source_path>
          2. LLM 编译为结构化 Wiki 页面
          3. WriteTool 写入 wiki/
          4. WikiRepository 记录元数据和链接
          5. 更新 wiki/log.md

        Args:
            source_path: 源文件路径（相对于 raw/sources/）

        Returns:
            IngestResponse 字典
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

        # 2. 调用 LLM 编译
        response = self.llm.chat(
            prompt=f"请处理以下源文件内容：\n\n{content}",
            system_prompt=SYSTEM_PROMPT_INGEST,
        )

        # 3. 解析 LLM 输出
        pages = self._parse_response(response)

        if not pages:
            return IngestResponse(
                status="success",
                message=f"No entities/concepts were extracted from '{source_path}'.",
            ).model_dump()

        pages_created = []
        pages_updated = []

        # 4. 写入文件、记录元数据和链接
        for path, page_content in pages.items():
            # 检查是否已存在
            existing = self.repo.get_page(path)
            if existing:
                pages_updated.append(path)
            else:
                pages_created.append(path)

            # 写入文件
            self.writer.write_page(path, page_content)

            # 提取元数据
            title = self._extract_title(page_content)
            tags = self._extract_tags(page_content)
            word_count = len(page_content)

            # 记录到数据库
            self.repo.add_page(
                path=path,
                title=title,
                page_type=self._guess_type(path),
                tags=tags,
                word_count=word_count,
            )

            # 提取并记录链接
            for target in self._extract_links(page_content):
                self.repo.add_link(path, target)
        # 5. 更新 log.md
        self._update_log(source_path, pages)

        return IngestResponse(
            status="success",
            pages_created=pages_created,
            pages_updated=pages_updated,
            message=f"Ingested '{source_path}': "
            f"{len(pages_created)} created, {len(pages_updated)} updated.",
        ).model_dump()

    def _guess_type(self, path: str) -> str:
        """根据路径前缀推测页面类型"""
        for t in ("entity", "concept", "source", "query"):
            if path.startswith(t) or path.startswith(f"{t}s/"):
                return t
        return "entity"

    def _update_log(self, source_path: str, pages: dict[str, str]) -> None:
        """更新 wiki/log.md 记录本次 ingest 操作"""
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
    # Query / Lint — Phase 2
    # ------------------------------------------------------------------

    def query(self, question: str) -> dict:
        """查询 Wiki 知识库并带引用回答"""
        raise NotImplementedError("Phase 2 实现")

    def lint(self) -> dict:
        """健康检查：断链、孤儿页、过时内容"""
        raise NotImplementedError("Phase 2 实现")
