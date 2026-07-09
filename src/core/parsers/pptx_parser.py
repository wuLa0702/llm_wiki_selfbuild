"""PPTX 解析器 — 提取文本为 Markdown 结构化格式"""
from src.core.logging_config import get_logger

logger = get_logger("parsers.pptx")


class PptxParser:
    """PPTX 文件解析器

    遍历幻灯片中的文本框、表格，提取文本。
    保留标题层级：slide title → `# `，正文 → 段落。
    表格提取为 Markdown 表格。
    """

    @staticmethod
    def parse(file_path: str) -> str:
        """解析 PPTX 文件为 Markdown 文本

        Args:
            file_path: .pptx 文件路径

        Returns:
            Markdown 格式的结构化文本
        """
        from pptx import Presentation
        from pptx.util import Inches, Pt

        prs = Presentation(file_path)
        pages: list[str] = []

        for slide_num, slide in enumerate(prs.slides, 1):
            slide_parts: list[str] = [f"# Slide {slide_num}"]

            for shape in slide.shapes:
                if shape.has_text_frame:
                    text = PptxParser._extract_text_frame(shape.text_frame)
                    if text.strip():
                        slide_parts.append(text)

                if shape.has_table:
                    table_text = PptxParser._extract_table(shape.table)
                    if table_text.strip():
                        slide_parts.append(table_text)

            pages.append("\n\n".join(slide_parts))

        result = "\n\n---\n\n".join(pages)
        logger.info("PPTX 解析完成 | file=%s slides=%d chars=%d",
                     file_path, len(prs.slides), len(result))
        return result

    @staticmethod
    def _extract_text_frame(tf) -> str:
        """提取文本框内容，保留段落结构"""
        paragraphs = []
        for para in tf.paragraphs:
            text = para.text.strip()
            if text:
                paragraphs.append(text)
        return "\n\n".join(paragraphs)

    @staticmethod
    def _extract_table(table) -> str:
        """提取表格为 Markdown 表格"""
        rows = []
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            rows.append("| " + " | ".join(cells) + " |")

        if rows:
            # 添加表头分隔行
            header = rows[0]
            cols = header.count("|") - 1
            separator = "| " + " | ".join(["---"] * cols) + " |"
            rows.insert(1, separator)

        return "\n".join(rows)
