"""
搜索工具 — 在 wiki 目录中搜索内容
"""


class SearchTool:
    """在 wiki 目录中搜索关键词"""

    def search(self, keyword: str) -> list[str]:
        """
        搜索包含关键词的 wiki 页面
        返回匹配文件的路径列表
        """
        raise NotImplementedError("Phase 2 实现")
