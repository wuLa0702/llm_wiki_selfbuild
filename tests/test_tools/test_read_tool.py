"""
ReadTool 单元测试
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
# 正常路径
# ---------------------------------------------------------------------------


def test_read_file_returns_content(raw_dir):
    """读取文件返回内容"""
    tool = ReadTool(base_dir=str(raw_dir))
    result = tool.read_file("hello.md")
    assert result == "# Hello World"


def test_read_file_empty(raw_dir):
    """读取空文件返回空字符串"""
    tool = ReadTool(base_dir=str(raw_dir))
    result = tool.read_file("empty.md")
    assert result == ""


def test_list_directory_returns_files(raw_dir):
    """列出目录下所有条目"""
    tool = ReadTool(base_dir=str(raw_dir))
    entries = tool.list_directory()
    # hello.md, empty.md, subdir
    assert "hello.md" in entries
    assert "empty.md" in entries
    assert "subdir" in entries


# ---------------------------------------------------------------------------
# 边界条件
# ---------------------------------------------------------------------------


def test_read_file_nested_path(raw_dir):
    """子目录下的文件可以正常读取"""
    tool = ReadTool(base_dir=str(raw_dir))
    result = tool.read_file("subdir/nested.md")
    assert result == "nested content"


def test_list_directory_empty_dir(tmp_path):
    """空目录返回空列表"""
    empty = tmp_path / "empty_raw"
    empty.mkdir()
    tool = ReadTool(base_dir=str(empty))
    assert tool.list_directory() == []


def test_list_directory_sorted(raw_dir):
    """返回结果按字母排序"""
    tool = ReadTool(base_dir=str(raw_dir))
    entries = tool.list_directory()
    assert entries == sorted(entries)


def test_list_subdir(raw_dir):
    """列出子目录内容"""
    tool = ReadTool(base_dir=str(raw_dir))
    entries = tool.list_directory("subdir")
    assert entries == ["nested.md"]


# ---------------------------------------------------------------------------
# 错误路径
# ---------------------------------------------------------------------------


def test_read_file_not_found(raw_dir):
    """文件不存在抛出 FileNotFoundError"""
    tool = ReadTool(base_dir=str(raw_dir))
    with pytest.raises(FileNotFoundError, match="not_found.md"):
        tool.read_file("not_found.md")


def test_read_file_outside_raw(raw_dir):
    """读取 base_dir 之外的文件抛出 PermissionError"""
    tool = ReadTool(base_dir=str(raw_dir))
    with pytest.raises(PermissionError):
        tool.read_file("../outside.md")


def test_read_file_traversal_dot_dot(raw_dir):
    """../ 路径穿越被拒绝"""
    tool = ReadTool(base_dir=str(raw_dir))
    with pytest.raises(PermissionError):
        tool.read_file("subdir/../../outside.md")


def test_read_file_absolute_path(raw_dir):
    """绝对路径被拒绝"""
    tool = ReadTool(base_dir=str(raw_dir))
    with pytest.raises(PermissionError):
        tool.read_file("/etc/passwd")


def test_list_directory_not_found(raw_dir):
    """目录不存在抛出 NotADirectoryError"""
    tool = ReadTool(base_dir=str(raw_dir))
    with pytest.raises(NotADirectoryError):
        tool.list_directory("nonexistent")
