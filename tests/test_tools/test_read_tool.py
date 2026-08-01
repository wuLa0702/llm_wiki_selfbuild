"""
ReadTool 单元测试 — 多格式文件读取
"""
import os

import pytest

from src.tools.read_tool import ReadTool


@pytest.fixture
def raw_dir(tmp_path):
    """创建一个模拟 raw/ 目录结构"""
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "hello.md").write_text("# Hello World", encoding="utf-8")
    (raw / "empty.md").write_text("", encoding="utf-8")
    sub = raw / "subdir"
    sub.mkdir()
    (sub / "nested.md").write_text("nested content", encoding="utf-8")
    return raw


# ---------------------------------------------------------------------------
# 文本格式（.md / .txt）
# ---------------------------------------------------------------------------


class TestTextFormat:
    """纯文本格式（.md, .txt）"""

    def test_read_md(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        assert tool.read_file("hello.md") == "# Hello World"

    def test_read_txt(self, raw_dir):
        (raw_dir / "readme.txt").write_text("plain text", encoding="utf-8")
        tool = ReadTool(base_dir=str(raw_dir))
        assert tool.read_file("readme.txt") == "plain text"

    def test_read_empty(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        assert tool.read_file("empty.md") == ""


# ---------------------------------------------------------------------------
# PDF 格式
# ---------------------------------------------------------------------------


class TestPdfFormat:
    """PDF 格式解析"""

    def test_read_pdf(self, raw_dir):
        """生成一个简单 PDF，验证文本提取"""
        from pypdf import PdfWriter

        pdf_path = os.path.join(raw_dir, "test.pdf")
        writer = PdfWriter()
        writer.add_blank_page(612, 792)  # Letter 大小

        # 用页面的 annots / 内容来写入文字
        page = writer.pages[0]
        page.merge_page(writer.add_blank_page(612, 792))  # dummy
        # 直接写内容流
        content = """
        /F1 12 Tf
        100 700 Td
        (Hello PDF World) Tj
        ET
        """
        page.merge_page(writer.add_blank_page(612, 792))
        # 实际上用 pypdf 的方法来插文字需要更复杂的操作
        # 改用 create_text 方式
        writer.close()

        # 重新用更简单的方法：直接写带内容的 PDF
        from io import BytesIO
        from pypdf import PdfWriter as PW, PdfReader

        buf = BytesIO()
        w = PW()
        w.add_blank_page(612, 792)
        w.write(buf)
        buf.seek(0)

        # 给 PDF 加一段文字最简单的方式是直接写 raw content
        # 这里创建一个真实含有文本的 PDF
        import struct

        pdf_content = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>stream
BT
/F1 12 Tf
100 700 Td
(Hello PDF World) Tj
ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000056 00000 n
0000000115 00000 n
0000000262 00000 n
0000000358 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
412
%%EOF"""

        with open(pdf_path, "wb") as f:
            f.write(pdf_content)

        tool = ReadTool(base_dir=str(raw_dir))
        result = tool.read_file("test.pdf")
        assert "Hello PDF World" in result
        assert "Page 1" in result

    def test_read_pdf_no_text(self, raw_dir):
        """空 PDF 返回占位消息"""
        from pypdf import PdfWriter

        pdf_path = os.path.join(raw_dir, "blank.pdf")
        writer = PdfWriter()
        writer.add_blank_page(612, 792)
        with open(pdf_path, "wb") as f:
            writer.write(f)

        tool = ReadTool(base_dir=str(raw_dir))
        result = tool.read_file("blank.pdf")
        assert "未提取到正文" in result


# ---------------------------------------------------------------------------
# DOCX 格式
# ---------------------------------------------------------------------------


class TestDocxFormat:
    """Word 文档格式解析"""

    def test_read_docx(self, raw_dir):
        """生成简单 DOCX，验证文本提取"""
        from docx import Document

        docx_path = os.path.join(raw_dir, "test.docx")
        doc = Document()
        doc.add_paragraph("Hello Word Document")
        doc.add_paragraph("第二段内容")
        doc.save(docx_path)

        tool = ReadTool(base_dir=str(raw_dir))
        result = tool.read_file("test.docx")
        assert "Hello Word Document" in result
        assert "第二段内容" in result

    def test_read_docx_table(self, raw_dir):
        """DOCX 中的表格内容被提取"""
        from docx import Document

        docx_path = os.path.join(raw_dir, "table.docx")
        doc = Document()
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = "Name"
        table.cell(0, 1).text = "Age"
        table.cell(1, 0).text = "Alice"
        table.cell(1, 1).text = "30"
        doc.save(docx_path)

        tool = ReadTool(base_dir=str(raw_dir))
        result = tool.read_file("table.docx")
        assert "Name" in result
        assert "Alice" in result
        assert "30" in result


# ---------------------------------------------------------------------------
# HTML 格式
# ---------------------------------------------------------------------------


class TestHtmlFormat:
    """HTML 格式解析"""

    def test_read_html(self, raw_dir):
        """HTML 去除标签，提取纯文本"""
        html = """<!DOCTYPE html>
<html><head><title>Test</title></head>
<body>
<h1>Title Here</h1>
<p>This is a paragraph.</p>
<ul><li>Item 1</li><li>Item 2</li></ul>
</body></html>"""
        (raw_dir / "page.html").write_text(html, encoding="utf-8")

        tool = ReadTool(base_dir=str(raw_dir))
        result = tool.read_file("page.html")
        assert "Title Here" in result
        assert "This is a paragraph" in result
        assert "Item 1" in result
        assert "Item 2" in result

    def test_read_html_strips_scripts(self, raw_dir):
        """script/style 标签被去除"""
        html = """<html><body>
<script>alert('xss')</script>
<style>.cls{color:red}</style>
<p>Real content</p>
</body></html>"""
        (raw_dir / "page.html").write_text(html, encoding="utf-8")

        tool = ReadTool(base_dir=str(raw_dir))
        result = tool.read_file("page.html")
        assert "Real content" in result
        assert "alert" not in result
        assert "color:red" not in result

    def test_read_html_empty(self, raw_dir):
        """空 HTML 返回占位消息"""
        (raw_dir / "empty.html").write_text("<html></html>", encoding="utf-8")
        tool = ReadTool(base_dir=str(raw_dir))
        result = tool.read_file("empty.html")
        assert "未提取到正文" in result


# ---------------------------------------------------------------------------
# CSV 格式
# ---------------------------------------------------------------------------


class TestCsvFormat:
    """CSV 格式解析"""

    def test_read_csv_basic(self, raw_dir):
        """CSV 内容被格式化为文本表格"""
        csv_content = "name,age,city\nAlice,30,Beijing\nBob,25,Shanghai\n"
        (raw_dir / "data.csv").write_text(csv_content, encoding="utf-8")

        tool = ReadTool(base_dir=str(raw_dir))
        result = tool.read_file("data.csv")
        assert "Alice" in result
        assert "Bob" in result
        assert "Beijing" in result
        assert "CSV:" in result

    def test_read_csv_semicolon(self, raw_dir):
        """分号分隔的 CSV"""
        csv_content = "name;age\nAlice;30\nBob;25\n"
        (raw_dir / "data.csv").write_text(csv_content, encoding="utf-8")

        tool = ReadTool(base_dir=str(raw_dir))
        result = tool.read_file("data.csv")
        assert "Alice" in result
        assert "Bob" in result

    def test_read_csv_empty(self, raw_dir):
        """空 CSV 返回占位消息"""
        (raw_dir / "empty.csv").write_text("", encoding="utf-8")
        tool = ReadTool(base_dir=str(raw_dir))
        result = tool.read_file("empty.csv")
        assert "空" in result


# ---------------------------------------------------------------------------
# 错误路径
# ---------------------------------------------------------------------------


class TestUnsupportedFormat:
    """不支持的格式"""

    def test_unsupported_extension(self, raw_dir):
        """不支持的文件扩展名抛出 ValueError"""
        (raw_dir / "data.json").write_text('{"key": "val"}', encoding="utf-8")
        tool = ReadTool(base_dir=str(raw_dir))
        with pytest.raises(ValueError, match="Unsupported"):
            tool.read_file("data.json")

    def test_unsupported_no_extension(self, raw_dir):
        """无扩展名抛出 ValueError"""
        (raw_dir / "README").write_text("content", encoding="utf-8")
        tool = ReadTool(base_dir=str(raw_dir))
        with pytest.raises(ValueError, match="Unsupported"):
            tool.read_file("README")


# ---------------------------------------------------------------------------
# 基础功能（原有测试）
# ---------------------------------------------------------------------------


class TestBasic:
    """原有 ReadTool 基础功能"""

    def test_read_file_returns_content(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        assert tool.read_file("hello.md") == "# Hello World"

    def test_read_file_empty(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        assert tool.read_file("empty.md") == ""

    def test_list_directory_returns_files(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        entries = tool.list_directory()
        assert "hello.md" in entries
        assert "empty.md" in entries
        assert "subdir" in entries

    def test_read_file_nested_path(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        assert tool.read_file("subdir/nested.md") == "nested content"

    def test_list_directory_empty_dir(self, tmp_path):
        empty = tmp_path / "empty_raw"
        empty.mkdir()
        tool = ReadTool(base_dir=str(empty))
        assert tool.list_directory() == []

    def test_list_directory_sorted(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        assert tool.list_directory() == sorted(tool.list_directory())

    def test_list_subdir(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        assert tool.list_directory("subdir") == ["nested.md"]


# ---------------------------------------------------------------------------
# 错误路径
# ---------------------------------------------------------------------------


class TestErrorPaths:
    """权限和路径校验"""

    def test_read_file_not_found(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        with pytest.raises(FileNotFoundError, match="not_found.md"):
            tool.read_file("not_found.md")

    def test_read_file_outside_raw(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        with pytest.raises(PermissionError):
            tool.read_file("../outside.md")

    def test_read_file_traversal_dot_dot(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        with pytest.raises(PermissionError):
            tool.read_file("subdir/../../outside.md")

    def test_read_file_absolute_path(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        with pytest.raises(PermissionError):
            tool.read_file("/etc/passwd")

    def test_list_directory_not_found(self, raw_dir):
        tool = ReadTool(base_dir=str(raw_dir))
        with pytest.raises(NotADirectoryError):
            tool.list_directory("nonexistent")


# ---------------------------------------------------------------------------
# 别名解析（2026-08-01 修复：LLM_WIKI_DATA_DIR 隔离模式下读侧目录一致性）
# ---------------------------------------------------------------------------


class TestAliasResolution:
    """base_dir 别名 "wiki"/"raw" 必须解析到数据目录（尊重 LLM_WIKI_DATA_DIR）"""

    def test_wiki_alias_resolves_to_data_dir(self, monkeypatch, tmp_path):
        import src.utils.path_resolver as pr
        app_dir = str(tmp_path)
        monkeypatch.setattr(pr, "APP_DATA_DIR", app_dir)

        from src.tools.read_tool import ReadTool
        tool = ReadTool("wiki")
        expected = os.path.join(app_dir, "wiki")
        assert os.path.normpath(tool.base_dir) == os.path.normpath(expected), (
            f"ReadTool('wiki').base_dir 应为 {expected}，实际 {tool.base_dir}"
        )

    def test_raw_alias_resolves_to_data_dir(self, monkeypatch, tmp_path):
        import src.utils.path_resolver as pr
        app_dir = str(tmp_path)
        monkeypatch.setattr(pr, "APP_DATA_DIR", app_dir)

        from src.tools.read_tool import ReadTool
        tool = ReadTool("raw")
        expected = os.path.join(app_dir, "raw")
        assert os.path.normpath(tool.base_dir) == os.path.normpath(expected)

    def test_absolute_base_dir_untouched(self):
        from src.tools.read_tool import ReadTool
        tool = ReadTool(base_dir="/abs/path")
        assert tool.base_dir == "/abs/path"
