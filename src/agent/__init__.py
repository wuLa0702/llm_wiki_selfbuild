"""
Chat Agent — 基于 LangGraph StateGraph 的知识问答代理

四层模块架构：
  perception/  — 感知层（消息处理、来源提取）
  planning/    — 规划层（图构建、节点、路由）
  memory/      — 记忆层（SQLite 持久化、摘要压缩）
  action/      — 执行层（工具、流式事件、响应格式化）

对外接口：
  build_agent() -> CompiledStateGraph      — 构建 Agent 图
  chat_stream(agent, messages)              — 无状态流式对话
  chat_stream_session(agent, content, ...)  — 多轮会话隔离版
"""

from src.agent.planning.graph import build_agent
from src.agent.action.stream import chat_stream
from src.agent.session import chat_stream_session

__all__ = ["build_agent", "chat_stream", "chat_stream_session"]
