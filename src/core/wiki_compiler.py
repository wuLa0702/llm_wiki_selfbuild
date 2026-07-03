"""
Wiki Compiler — Agent 主流程编排
"""
from typing import Optional


class WikiCompiler:
    """Agent 主流程：协调工具和 LLM 完成 Ingest/Query/Lint 操作"""

    def __init__(self):
        pass

    def ingest(self, source_path: str) -> dict:
        """
        Ingest 一个源文件到 Wiki 知识库
        1. 读取 raw/ 下的源文件
        2. 调用 LLM 提取实体和概念
        3. 生成 Wiki 页面（含双向链接）
        4. 更新 index.md 和 log.md
        """
        raise NotImplementedError("Phase 1 实现")

    def query(self, question: str) -> dict:
        """查询 Wiki 知识库并带引用回答"""
        raise NotImplementedError("Phase 2 实现")

    def lint(self) -> dict:
        """健康检查：断链、孤儿页、过时内容"""
        raise NotImplementedError("Phase 2 实现")
