"""
Agent 构建 + 流式对话接口

导出接口:
  build_agent() -> CompiledStateGraph
  chat_stream(messages) -> AsyncIterator[dict]

接口固定，换 LangGraph 时路由层和前端不改。
"""
import logging
from collections.abc import AsyncIterator

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.agent.tools import search_wiki, read_page, query_graph
from src.llm.adapter import LLMAdapter

logger = logging.getLogger("agent")

# System Prompt（与最终方案一致）
SYSTEM_PROMPT = """你是 LLM Wiki 的知识助手。你可以搜索、阅读、分析知识库中的内容来回答用户问题。

规则：
1. 回答必须基于 Wiki 页面内容，不要编造信息
2. 不确定时先调用 search_wiki 找到相关页面，再用 read_page 获取详情
3. 引用页面时使用 [[页面路径]] 格式，用户可点击跳转
4. 如果知识库中没有相关内容，明确告知用户，不要编造
5. 使用中文回答（除非用户用其他语言提问）
6. 回答要简洁准确，适当使用 Markdown 格式"""

# P1 工具列表：全部只读
P1_TOOLS = [search_wiki, read_page]

# P1.5 可选加入
P1_5_TOOLS = [query_graph]

# P1 硬窗口保护：超出此轮数的历史被丢弃，防止 token 爆炸
# P2 会用 ConversationSummaryMemory 替代简单截断
MAX_MESSAGE_TURNS = 20


def build_agent() -> object:
    """构建 ReAct Agent（CompiledStateGraph）

    Returns:
        CompiledStateGraph: LangChain v1 agent graph
    """
    adapter = LLMAdapter()
    llm = adapter._llm  # ChatOpenAI 实例，已配置 DeepSeek provider

    agent = create_agent(
        model=llm,
        tools=P1_TOOLS.copy(),
        system_prompt=SYSTEM_PROMPT,
        name="wiki_agent",
    )
    logger.info("Agent 构建完成 | tools=%s", [t.name for t in P1_TOOLS])
    return agent


async def chat_stream(
    agent: object,
    messages: list[dict],
) -> AsyncIterator[dict]:
    """流式对话接口 — 生产 SSE 事件

    Args:
        agent: build_agent() 返回的 agent 实例
        messages: 对话历史 [{"role": "user"|"assistant", "content": "..."}, ...]

    Yields:
        事件 dict，类型：
          {"type": "token", "content": "..."}
          {"type": "tool_start", "tool": "...", "input": {...}}
          {"type": "tool_end", "tool": "...", "output": "..."}
          {"type": "done", "sources": [...]}
          {"type": "error", "message": "..."}
    """
    # 转换消息格式
    lc_messages = []
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

    # P1 硬窗口保护：保留最近 MAX_MESSAGE_TURNS 轮对话，防止 token 爆炸
    # 保留第一个 system 消息（如果存在）以确保 Agent 人格不丢失
    system_msgs = [m for m in lc_messages if isinstance(m, SystemMessage)]
    non_system = [m for m in lc_messages if not isinstance(m, SystemMessage)]
    if len(non_system) > MAX_MESSAGE_TURNS:
        logger.warning(
            "消息超窗口 | total=%d keeping=%d",
            len(non_system),
            MAX_MESSAGE_TURNS,
        )
        non_system = non_system[-MAX_MESSAGE_TURNS:]
    lc_messages = system_msgs + non_system

    sources: list[str] = []

    try:
        # 使用 astream_events 获取流式事件
        async for event in agent.astream_events(
            {"messages": lc_messages},
            version="v1",
        ):
            kind = event.get("event", "")
            event_id = event.get("run_id", "")
            name = event.get("name", "")
            data = event.get("data", {})

            if kind == "on_chat_model_stream":
                # LLM token 级输出
                chunk = data.get("chunk", None)
                if chunk is not None:
                    content = getattr(chunk, "content", "")
                    if content:
                        yield {"type": "token", "content": content}

            elif kind == "on_tool_start":
                # 工具调用开始
                tool_input = data.get("input", {})
                yield {
                    "type": "tool_start",
                    "tool": name,
                    "input": tool_input,
                }

            elif kind == "on_tool_end":
                # 工具调用结束 — 从输出中提取来源页面
                output = data.get("output", "")
                output_str = str(output) if output else ""
                yield {
                    "type": "tool_end",
                    "tool": name,
                    "output": output_str[:500],
                }
                # 收集 wiki 页面路径作为来源
                if output_str:
                    import re
                    wiki_paths = re.findall(r'`([^`]+\.md)`', output_str)
                    sources.extend(wiki_paths)

    except Exception as e:
        logger.error("Agent 流式调用失败 | error=%s", e)
        yield {"type": "error", "message": f"Agent 调用失败: {e}"}
        return

    # 去重来源
    unique_sources = list(dict.fromkeys(sources))
    yield {"type": "done", "sources": unique_sources}
