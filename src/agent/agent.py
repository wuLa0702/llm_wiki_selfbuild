"""
Agent 构建 + 流式对话接口

导出接口:
  build_agent() -> CompiledStateGraph
  chat_stream(messages) -> AsyncIterator[dict]

接口固定，换 LangGraph 时路由层和前端不改。
"""

import logging
import os
import re
from collections.abc import AsyncIterator
from typing import Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode

from src.agent.tools import read_page, search_wiki

load_dotenv()
logger = logging.getLogger("agent")


# ── 系统提示 ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是 LLM Wiki 的知识助手。你可以搜索、阅读、分析知识库中的内容来回答用户问题。

规则：
1. 回答必须基于 Wiki 页面内容，不要编造信息
2. 不确定时先调用 search_wiki 找到相关页面，再用 read_page 获取详情
3. 引用页面时使用 [[页面路径]] 格式，用户可点击跳转
4. 如果知识库中没有相关内容，明确告知用户，不要编造
5. 使用中文回答（除非用户用其他语言提问）
6. 回答要简洁准确，适当使用 Markdown 格式"""


# ── 配置 ──────────────────────────────────────────────────────────────────────

P1_TOOLS = [search_wiki, read_page]

# 硬窗口保护：超出此轮数的历史被丢弃，防止 token 爆炸
# P2 会用 ConversationSummaryMemory 替代简单截断
MAX_MESSAGE_TURNS = 20


# ── 图状态定义 ────────────────────────────────────────────────────────────────

class AgentState(TypedDict):
    """LangGraph 图共享状态

    messages: 对话 + 工具调用全链路记录，元素必须是 BaseMessage 子类
    """
    messages: list[BaseMessage]


# ── LLM 初始化 ────────────────────────────────────────────────────────────────

llm = ChatOpenAI(
    model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
    api_key=os.environ["DEEPSEEK_API_KEY"],
    base_url=os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1"),
    timeout=15,
    max_retries=1,
)
llm_with_tools = llm.bind_tools(P1_TOOLS)


# ── 图节点 ────────────────────────────────────────────────────────────────────

def call_model(state: AgentState) -> dict:
    """调 LLM，返回响应追加到 messages"""
    response = llm_with_tools.invoke(state["messages"])
    return {"messages": [response]}


tool_node = ToolNode(P1_TOOLS)


def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    """判断 LLM 输出是否需要执行工具——图分支路由函数

    存在 tool_calls → 跳转 tools 节点执行工具
    无工具调用     → 结束对话流程
    """
    last_msg = state["messages"][-1]
    if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
        return "tools"
    return "__end__"


# ── 图构建 ────────────────────────────────────────────────────────────────────

builder = StateGraph(AgentState)
builder.add_node("agent", call_model)
builder.add_node("tools", tool_node)
builder.set_entry_point("agent")
builder.add_edge("tools", "agent")
builder.add_conditional_edges("agent", should_continue)

app = builder.compile(checkpointer=MemorySaver())


def build_agent() -> CompiledStateGraph:
    """构建 ReAct Agent（CompiledStateGraph）"""
    logger.info("Agent 构建完成 | tools=%s", [t.name for t in P1_TOOLS])
    return app


# ── 流式对话接口 ──────────────────────────────────────────────────────────────

async def chat_stream(
    agent: CompiledStateGraph,
    messages: list[dict],
) -> AsyncIterator[dict]:
    """流式对话接口 —— 生产 SSE 事件

    Args:
        agent: build_agent() 返回的 CompiledStateGraph 实例
        messages: [{"role": "user"|"assistant"|"system", "content": "..."}, ...]

    Yields:
        {"type": "token", "content": "..."}      — LLM token 级输出
        {"type": "tool_start", "tool": "...", "input": {...}}  — 工具调用开始
        {"type": "tool_end", "tool": "...", "output": "..."}   — 工具调用结束
        {"type": "done", "sources": [...]}        — 对话结束，返回引用来源
        {"type": "error", "message": "..."}       — 错误事件
    """
    lc_messages: list[BaseMessage] = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            lc_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            lc_messages.append(AIMessage(content=content))
        elif role == "system":
            lc_messages.append(SystemMessage(content=content))

    if not lc_messages:
        yield {"type": "error", "message": "消息列表为空"}
        return

    # 窗口截断：保留 SystemMessage（人格设定）+ 最近 MAX_MESSAGE_TURNS 轮对话
    system_msgs = [m for m in lc_messages if isinstance(m, SystemMessage)]
    non_system = [m for m in lc_messages if not isinstance(m, SystemMessage)]
    if len(non_system) > MAX_MESSAGE_TURNS:
        logger.warning(
            "消息超窗口 | total=%d keeping=%d", len(non_system), MAX_MESSAGE_TURNS
        )
        non_system = non_system[-MAX_MESSAGE_TURNS:]
    lc_messages = system_msgs + non_system

    # 收集工具调用中引用的 Wiki 页面路径，用于最终返回来源列表
    wiki_path_source: list[str] = []

    try:
        async for event in agent.astream_events(
            {"messages": lc_messages},
            version="v1",
        ):
            kind = event.get("event", "")
            name = event.get("name", "")
            data = event.get("data", {})

            if kind == "on_chat_model_stream":
                chunk = data.get("chunk")
                if chunk is not None:
                    content = getattr(chunk, "content", "")
                    if content:
                        yield {"type": "token", "content": content}

            elif kind == "on_tool_start":
                yield {
                    "type": "tool_start",
                    "tool": name,
                    "input": data.get("input", {}),
                }

            elif kind == "on_tool_end":
                output = data.get("output", "")
                output_str = str(output) if output else ""
                yield {
                    "type": "tool_end",
                    "tool": name,
                    "output": output_str[:500],
                }
                if output_str:
                    wiki_paths = re.findall(r'`([^`]+\.md)`', output_str)
                    wiki_path_source.extend(wiki_paths)

    except Exception as e:
        logger.error("Agent 流式调用失败 | error=%s", e)
        yield {"type": "error", "message": f"Agent 调用失败: {e}"}
        return

    yield {"type": "done", "sources": list(dict.fromkeys(wiki_path_source))}
