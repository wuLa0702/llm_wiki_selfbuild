"""
记忆管理 — 短期/长期记忆
"""


class WikiMemory:
    """Agent 记忆管理
    - 短期记忆：当前会话上下文
    - 长期记忆：Wiki 文件本身即是持久记忆
    - 索引：index.md
    - 审计：log.md
    """

    def __init__(self):
        pass

    def load_context(self, query: str) -> str:
        """加载相关上下文"""
        raise NotImplementedError("Phase 2 实现")

    def save_to_log(self, action: str, detail: dict):
        """记录操作日志"""
        raise NotImplementedError("Phase 2 实现")
