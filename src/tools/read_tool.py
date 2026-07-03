"""
读取工具 — 读取 raw/ 目录下的源文件（只读，路径权限校验）
"""


class ReadTool:
    """读取 raw/ 目录下的文件内容，不能写"""

    def __init__(self):
        self.allowed_prefix = "raw"

    def read_file(self, filename: str) -> str:
        """
        读取 raw 目录下的文件
        权限校验：只能读 raw/，拒绝跨目录攻击
        """
        raise NotImplementedError("Phase 1 实现")

    def list_directory(self, directory: str) -> list[str]:
        """列出目录内容"""
        raise NotImplementedError("Phase 1 实现")
