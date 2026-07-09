"""文档解析器 — 统一入口

自动检测文件扩展名并选择合适的解析器。
支持：.pptx, .xlsx, .md, .txt, .html, .csv
"""
import os

from src.core.logging_config import get_logger

logger = get_logger("parsers")

# 注册解析器（模块级 import，避免循环依赖）
_PARSERS: dict[str, str] = {}


def _register_parsers():
    """延迟注册解析器"""
    if _PARSERS:
        return
    try:
        from src.core.parsers.pptx_parser import PptxParser
        _PARSERS[".pptx"] = "pptx"
        _PARSERS[".ppt"] = "pptx"
    except ImportError:
        logger.debug("PPTX parser not available")
    try:
        from src.core.parsers.xlsx_parser import XlsxParser
        _PARSERS[".xlsx"] = "xlsx"
        _PARSERS[".xls"] = "xlsx"
    except ImportError:
        logger.debug("XLSX parser not available")


def parse_document(file_path: str) -> str:
    """解析文档为纯文本

    Args:
        file_path: 文件路径

    Returns:
        解析后的纯文本（保留结构化信息）

    Raises:
        ValueError: 不支持的文件格式或解析失败
    """
    _register_parsers()

    ext = os.path.splitext(file_path)[1].lower()

    if ext in (".md", ".txt"):
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    elif ext in (".html", ".htm"):
        try:
            from bs4 import BeautifulSoup
            with open(file_path, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
                return soup.get_text(separator="\n", strip=True)
        except ImportError:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()
    elif ext == ".csv":
        import csv
        import io
        lines = []
        with open(file_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                lines.append(" | ".join(row))
        return "\n".join(lines)
    elif ext == ".pptx":
        from src.core.parsers.pptx_parser import PptxParser
        return PptxParser.parse(file_path)
    elif ext == ".xlsx":
        from src.core.parsers.xlsx_parser import XlsxParser
        return XlsxParser.parse(file_path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")


def get_supported_extensions() -> list[str]:
    """返回支持的扩展名列表"""
    _register_parsers()
    base = [".md", ".txt", ".html", ".htm", ".csv"]
    base.extend(_PARSERS.keys())
    return sorted(set(base))
