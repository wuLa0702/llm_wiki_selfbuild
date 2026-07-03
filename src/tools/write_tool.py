"""
写入工具 — 写入 wiki/ 目录（权限校验，防止越权）
"""


class WriteTool:
    """在 wiki 目录下创建或更新 Markdown 页面"""

    def __init__(self):
        self.allowed_prefix = "wiki"

    def write_page(self, relative_path: str, content: str) -> str:
        """
        写入 wiki 页面
        权限校验：只能写 wiki/，拒绝路径穿越攻击
        """
        raise NotImplementedError("Phase 1 实现")
