"""
写入工具 — 写入 wiki/ 目录（权限校验，防止越权）
"""
import os

from src.core.validator import WikiValidator
from src.tools.path_utils import _resolve_alias, safe_path


class WriteTool:
    """在 wiki 目录下创建或更新 Markdown 页面"""

    def __init__(self, base_dir: str = "wiki") -> None:
        """
        Args:
            base_dir: 允许写入的根目录（默认 "wiki"），可注入用于测试

        修复 2026-08-01：构造时解析 "wiki" 别名 → get_wiki_dir()，
        与 ReadTool 保持一致（此前 base_dir 裸存相对字符串，依赖 safe_path
        内部别名解析才能写到正确目录）。
        """
        self.base_dir = _resolve_alias(base_dir)

    def write_page(self, relative_path: str, content: str, validate: bool = True) -> str:
        """
        写入 wiki 页面

        Args:
            relative_path: 相对于 base_dir 的文件路径
            content: 要写入的内容
            validate: 是否执行内容质量校验（默认 True）

        Returns:
            写入完成的相对路径

        Raises:
            PermissionError: 路径越权或穿越攻击
            ValidatorError: 内容校验失败
        """
        if validate:
            WikiValidator.validate_all(relative_path, content)

        full_path = safe_path(self.base_dir, relative_path)

        # 自动创建中间目录
        parent_dir = os.path.dirname(full_path)
        os.makedirs(parent_dir, exist_ok=True)

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        return os.path.normpath(relative_path)
