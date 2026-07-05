"""
写入工具 — 写入 wiki/ 目录（权限校验，防止越权）
"""
import os

from src.tools.path_utils import safe_path


class WriteTool:
    """在 wiki 目录下创建或更新 Markdown 页面"""

    def __init__(self, base_dir: str = "wiki") -> None:
        """
        Args:
            base_dir: 允许写入的根目录（默认 "wiki"），可注入用于测试
        """
        self.base_dir = base_dir

    def write_page(self, relative_path: str, content: str) -> str:
        """
        写入 wiki 页面

        Args:
            relative_path: 相对于 base_dir 的文件路径
            content: 要写入的内容

        Returns:
            写入完成的相对路径

        Raises:
            PermissionError: 路径越权或穿越攻击
        """
        full_path = safe_path(self.base_dir, relative_path)

        # 自动创建中间目录
        parent_dir = os.path.dirname(full_path)
        os.makedirs(parent_dir, exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return os.path.normpath(relative_path)
