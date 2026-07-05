"""
读取工具 — 读取 raw/ 目录下的源文件（只读，路径权限校验）
"""
import os

from src.tools.path_utils import safe_path


class ReadTool:
    """读取 raw/ 目录下的文件内容，不能写"""

    def __init__(self, base_dir: str = "raw") -> None:
        """
        Args:
            base_dir: 允许读取的根目录（默认 "raw"），可注入用于测试
        """
        self.base_dir = base_dir

    def read_file(self, filename: str) -> str:
        """
        读取文件内容

        Args:
            filename: 相对于 base_dir 的文件路径

        Returns:
            文件内容

        Raises:
            FileNotFoundError: 文件不存在
            PermissionError: 路径越权或穿越攻击
        """
        full_path = safe_path(self.base_dir, filename)

        if not os.path.isfile(full_path):
            raise FileNotFoundError(f"File not found: {filename}")

        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

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
