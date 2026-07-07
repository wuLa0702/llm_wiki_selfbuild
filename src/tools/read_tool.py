"""
读取工具 — 读取 raw/ 目录下的源文件（只读，路径权限校验）

支持多格式：.md .txt .pdf .docx .html .csv
扩展名自动识别，调用对应的解析器提取文本。
"""
import csv
import io
import os
from pathlib import Path

from src.core.logging_config import get_logger
from src.tools.path_utils import safe_path

logger = get_logger("read_tool")

# 格式名称 → 读取方法映射，用于错误信息
FORMAT_NAMES = {
    ".pdf": "PDF",
    ".docx": "Word 文档",
    ".html": "HTML",
    ".htm": "HTML",
    ".csv": "CSV",
    ".md": "Markdown",
    ".txt": "文本",
}


class ReadTool:
    """读取 raw/ 目录下的文件内容，不能写"""

    def __init__(self, base_dir: str = "raw") -> None:
        """
        Args:
            base_dir: 允许读取的根目录（默认 "raw"），可注入用于测试
        """
        self.base_dir = base_dir

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def read_file(self, filename: str) -> str:
        """
        读取文件内容，根据扩展名自动选择解析方式

        Args:
            filename: 相对于 base_dir 的文件路径

        Returns:
            文件内容（纯文本）

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 路径越权或穿越攻击
            ValueError: 不支持的格式
        """
        full_path = safe_path(self.base_dir, filename)

        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"File not found: {filename}")

        ext = Path(filename).suffix.lower()

        reader = self._get_reader(ext)
        if reader is None:
            fmt = FORMAT_NAMES.get(ext, ext.upper())
            raise ValueError(
                f"Unsupported file format '{fmt} ({ext})': {filename}. "
                "Supported: .md .txt .pdf .docx .html .csv"
            )

        try:
            return reader(full_path, filename)
        except Exception as exc:
            logger.warning("文件解析失败 | path=%s ext=%s error=%s",
                           filename, ext, exc)
            raise

    @staticmethod
    def _get_reader(ext: str):
        """根据扩展名返回对应的读取函数"""
        readers = {
            ".md": ReadTool._read_text,
            ".txt": ReadTool._read_text,
            ".pdf": ReadTool._read_pdf,
            ".docx": ReadTool._read_docx,
            ".html": ReadTool._read_html,
            ".htm": ReadTool._read_html,
            ".csv": ReadTool._read_csv,
        }
        return readers.get(ext)

    def list_directory(self, directory: str = "") -> list[str]:
        """
        列出目录内容

        Args:
            directory: 相对于 base_dir 的目录路径（空字符串表示根目录）

        Returns:
            排序后的文件/目录名列表

        Raises:
            NotADirectoryError: 目录不存在
            PermissionError: 路径越权或穿越攻击
        """
        full_path = safe_path(self.base_dir, directory)

        if not os.path.isdir(full_path):
            raise NotADirectoryError(f"Directory not found: {directory}")

        entries = os.listdir(full_path)
        return sorted(entries)

    # ------------------------------------------------------------------
    # 格式解析器
    # ------------------------------------------------------------------

    @staticmethod
    def _read_text(full_path: str, filename: str) -> str:
        """读取纯文本文件（.md / .txt）"""
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    @staticmethod
    def _read_pdf(full_path: str, filename: str) -> str:
        """读取 PDF 文件，提取全部文本"""
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ImportError(
                "PDF 解析需要 pypdf 库：pip install pypdf"
            )

        reader = PdfReader(full_path)
        pages = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text()
            if text and text.strip():
                pages.append(f"--- Page {i + 1} ---\n{text.strip()}")

        if not pages:
            logger.warning("PDF 未提取到文本 | path=%s pages=%d", filename, len(reader.pages))
            return "（PDF 文件未提取到正文内容）"

        result = "\n\n".join(pages)
        logger.debug("PDF 解析完成 | path=%s pages=%d chars=%d",
                     filename, len(reader.pages), len(result))
        return result

    @staticmethod
    def _read_docx(full_path: str, filename: str) -> str:
        """读取 Word 文档，提取全部文本"""
        try:
            from docx import Document
        except ImportError:
            raise ImportError(
                "Word 文档解析需要 python-docx 库：pip install python-docx"
            )

        doc = Document(full_path)
        paragraphs = []
        for para in doc.paragraphs:
            if para.text.strip():
                paragraphs.append(para.text.strip())

        # 也提取表格内容
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                paragraphs.append(" | ".join(cells))

        if not paragraphs:
            return "（Word 文档未提取到正文内容）"

        result = "\n\n".join(paragraphs)
        logger.debug("DOCX 解析完成 | path=%s chars=%d", filename, len(result))
        return result

    @staticmethod
    def _read_html(full_path: str, filename: str) -> str:
        """读取 HTML 文件，提取纯文本"""
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError(
                "HTML 解析需要 beautifulsoup4 库：pip install beautifulsoup4"
            )

        with open(full_path, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f.read(), "html.parser")

        # 移除脚本和样式
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)

        if not text:
            return "（HTML 文件未提取到正文内容）"

        logger.debug("HTML 解析完成 | path=%s chars=%d", filename, len(text))
        return text

    @staticmethod
    def _read_csv(full_path: str, filename: str) -> str:
        """读取 CSV 文件，格式化为文本表格"""
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
            sample = content[:1024]

        # 探测分隔符
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = None

        rows = list(csv.reader(io.StringIO(content), dialect=dialect or csv.excel))

        if not rows:
            return "（CSV 文件为空）"

        # 格式化：第一行做表头，其余做数据行
        lines = [f"# CSV: {filename}", f"行数: {len(rows)}, 列数: {len(rows[0]) if rows else 0}"]
        lines.append("")

        # 列宽对齐（每列取最宽值）
        col_count = max(len(row) for row in rows) if rows else 0
        if col_count > 0:
            col_widths = []
            for col_idx in range(col_count):
                widths = [len(str(row[col_idx])) for row in rows if col_idx < len(row)]
                col_widths.append(max(widths) if widths else 0)
            col_widths = [min(w, 60) for w in col_widths]  # 限制列宽

            for row_idx, row in enumerate(rows):
                padded = []
                for col_idx in range(col_count):
                    val = str(row[col_idx]) if col_idx < len(row) else ""
                    if len(val) > 60:
                        val = val[:57] + "..."
                    padded.append(val.ljust(col_widths[col_idx]))
                lines.append("  ".join(padded))

                if row_idx == 0:  # 表头后加分隔线
                    lines.append("-" * min(sum(col_widths) + 3 * col_count, 120))

        result = "\n".join(lines)
        logger.debug("CSV 解析完成 | path=%s rows=%d chars=%d",
                     filename, len(rows), len(result))
        return result
