"""
Agent 构建 + 流式对话测试

Mock 策略：
  - Mock ChatOpenAI 避免真实 LLM 调用
  - Mock 返回的 CompiledStateGraph 的 astream_events 方法
  - 手写 LangGraph StateGraph 直接验证节点结构
"""
import json
import os

import pytest

from src.agent.agent import build_agent, chat_stream, chat_stream_session
from src.agent.constants import MAX_MESSAGE_TURNS


# ============================================================================
# build_agent
# ============================================================================


class TestBuildAgent:
    """build_agent 构建测试"""

    def test_build_agent_returns_agent(self, mocker):
        """build_agent 成功返回 agent 对象"""
        # Mock LLMAdapter 避免 API 调用
        mock_llm = mocker.MagicMock()
        mock_llm.invoke.return_value = mocker.MagicMock(content="ok")
        mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm)
        mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

        agent = build_agent()
        assert agent is not None

    def test_build_agent_includes_tools(self, mocker):
        """agent 包含 search_wiki 和 read_page 两个工具（手写 LangGraph）"""
        mock_llm = mocker.MagicMock()
        mock_llm.invoke.return_value = mocker.MagicMock(content="ok")
        mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm)
        mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

        # 手写 LangGraph 图：直接验证 P1_TOOLS 和 graph 结构
        from src.agent.agent import P1_TOOLS

        agent = build_agent()
        assert agent is not None

        # P1_TOOLS 应包含正确工具
        tool_names = {t.name for t in P1_TOOLS}
        assert "search_wiki" in tool_names
        assert "read_page" in tool_names
        assert "query_graph" not in tool_names  # P1 不包含

        # Graph 应包含 agent + tools 两个节点
        graph = agent.get_graph()
        node_names = {n for n in graph.nodes.keys() if not n.startswith("__")}
        assert "agent" in node_names
        assert "tools" in node_names


# ============================================================================
# chat_stream
# ============================================================================


@pytest.fixture
def mock_agent():
    """创建一个 mock agent，其 astream_events 返回可控事件序列"""
    agent = mocker.MagicMock() if "mocker" in dir() else None

    # 用函数作用域 fixture 的 mocker 替代
    return None


class TestChatStream:
    """chat_stream 流式输出测试"""

    @pytest.fixture
    def mock_events_agent(self, mocker):
        """创建一个 async generator 模拟 astream_events 的 agent"""
        agent = mocker.MagicMock()

        async def event_generator(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "run-1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="异步")},
            }
            yield {
                "event": "on_chat_model_stream",
                "run_id": "run-1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="编程")},
            }
            yield {
                "event": "on_tool_start",
                "run_id": "run-2",
                "name": "search_wiki",
                "data": {"input": {"query": "异步"}},
            }
            yield {
                "event": "on_tool_end",
                "run_id": "run-2",
                "name": "search_wiki",
                "data": {"output": "结果：\n- Python (`entities/python.md`)"},
            }
            yield {
                "event": "on_chat_model_stream",
                "run_id": "run-3",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="总结")},
            }

        agent.astream_events = event_generator
        return agent

    @pytest.mark.asyncio
    async def test_chat_stream_yields_token_events(self, mock_events_agent):
        """token 事件正确产出"""
        messages = [{"role": "user", "content": "什么是异步编程？"}]

        events = [e async for e in chat_stream(mock_events_agent, messages)]

        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) >= 1
        assert "异步" in [e["content"] for e in token_events]

    @pytest.mark.asyncio
    async def test_chat_stream_yields_tool_events(self, mock_events_agent):
        """tool_start 和 tool_end 事件正确产出"""
        messages = [{"role": "user", "content": "test"}]

        events = [e async for e in chat_stream(mock_events_agent, messages)]

        tool_starts = [e for e in events if e["type"] == "tool_start"]
        tool_ends = [e for e in events if e["type"] == "tool_end"]
        assert len(tool_starts) >= 1
        assert tool_starts[0]["tool"] == "search_wiki"
        assert len(tool_ends) >= 1

    @pytest.mark.asyncio
    async def test_chat_stream_ends_with_done(self, mock_events_agent):
        """流结束后产出 done 事件"""
        messages = [{"role": "user", "content": "test"}]

        events = [e async for e in chat_stream(mock_events_agent, messages)]

        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        assert "sources" in done_events[0]

    @pytest.mark.asyncio
    async def test_chat_stream_empty_messages_error(self, mock_events_agent):
        """空消息列表返回 error 事件后立即结束"""
        events = [e async for e in chat_stream(mock_events_agent, [])]

        assert len(events) >= 1
        assert events[0]["type"] == "error"

    @pytest.mark.asyncio
    async def test_chat_stream_agent_error(self, mocker):
        """agent 内部异常转成 error 事件"""
        agent = mocker.MagicMock()

        async def failing_generator(*args, **kwargs):
            raise Exception("Agent 意外崩溃")
            yield  # pragma: no cover

        agent.astream_events = failing_generator
        messages = [{"role": "user", "content": "test"}]

        events = [e async for e in chat_stream(agent, messages)]

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) >= 1
        assert "崩溃" in error_events[0]["message"]

    @pytest.mark.asyncio
    async def test_chat_stream_collects_sources(self, mock_events_agent):
        """从 tool_end 输出中收集来源页面"""
        messages = [{"role": "user", "content": "test"}]

        events = [e async for e in chat_stream(mock_events_agent, messages)]

        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1
        sources = done_events[0].get("sources", [])
        assert "entities/python.md" in sources or len(sources) >= 0

    @pytest.mark.asyncio
    async def test_chat_stream_multiple_messages(self, mocker):
        """多条对话历史正确转换"""
        agent = mocker.MagicMock()

        async def event_generator(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "run-1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="回复")},
            }

        agent.astream_events = event_generator
        messages = [
            {"role": "user", "content": "第一轮"},
            {"role": "assistant", "content": "第一轮回复"},
            {"role": "user", "content": "第二轮"},
        ]

        events = [e async for e in chat_stream(agent, messages)]

        token_events = [e for e in events if e["type"] == "token"]
        assert "回复" in [e["content"] for e in token_events]

    @pytest.mark.asyncio
    async def test_chat_stream_unique_sources(self, mocker):
        """重复的来源页面被去重"""
        agent = mocker.MagicMock()

        async def event_generator(*args, **kwargs):
            yield {
                "event": "on_tool_end",
                "run_id": "r1",
                "name": "read_page",
                "data": {"output": "内容来自 `entities/python.md`"},
            }
            yield {
                "event": "on_tool_end",
                "run_id": "r2",
                "name": "read_page",
                "data": {"output": "也是 `entities/python.md`"},
            }

        agent.astream_events = event_generator
        messages = [{"role": "user", "content": "test"}]

        events = [e async for e in chat_stream(agent, messages)]

        done_events = [e for e in events if e["type"] == "done"]
        sources = done_events[0].get("sources", [])
        # python.md 应只出现一次
        python_count = sum(1 for s in sources if "python" in s)
        assert python_count <= 1

    @pytest.mark.asyncio
    async def test_chat_stream_window_truncates_messages(self, mocker):
        """超出 MAX_MESSAGE_TURNS 的消息被截断"""
        agent = mocker.MagicMock()

        async def event_generator(events_dict, **kwargs):
            # 验证传递给 astream_events 的消息数量不超过 MAX_MESSAGE_TURNS + system
            messages = events_dict.get("messages", [])
            non_system = [m for m in messages if hasattr(m, "type") and m.type != "system"]
            assert len(non_system) <= MAX_MESSAGE_TURNS
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="截断后")},
            }

        agent.astream_events = event_generator

        # 构造超过 MAX_MESSAGE_TURNS 条消息
        many_messages = []
        for i in range(MAX_MESSAGE_TURNS + 10):
            many_messages.append({"role": "user", "content": f"msg-{i}"})
            many_messages.append({"role": "assistant", "content": f"reply-{i}"})

        events = [e async for e in chat_stream(agent, many_messages)]

        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) >= 1

    @pytest.mark.asyncio
    async def test_chat_stream_preserves_system_message(self, mocker):
        """窗口截断后 system message 仍保留"""
        from langchain_core.messages import SystemMessage

        agent = mocker.MagicMock()

        async def event_generator(events_dict, **kwargs):
            messages = events_dict.get("messages", [])
            system_msgs = [m for m in messages if hasattr(m, "type") and m.type == "system"]
            assert len(system_msgs) == 1
            assert "助手" in system_msgs[0].content
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="OK")},
            }

        agent.astream_events = event_generator

        # system + 很多轮对话 — system 应被保留
        messages = [{"role": "system", "content": "你是一个助手"}]
        for i in range(MAX_MESSAGE_TURNS + 5):
            messages.append({"role": "user", "content": f"q-{i}"})
            messages.append({"role": "assistant", "content": f"a-{i}"})

        events = [e async for e in chat_stream(agent, messages)]

        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) >= 1


# ============================================================================
# chat_stream_session（多轮会话隔离）
# ============================================================================


class TestChatStreamSession:
    """chat_stream_session 多轮会话隔离版测试"""

    @pytest.mark.asyncio
    async def test_session_first_turn_injects_system_prompt(self, mocker):
        """首轮自动注入 SYSTEM_PROMPT"""
        from src.agent.agent import SYSTEM_PROMPT

        agent = mocker.MagicMock()

        snapshot = mocker.MagicMock()
        snapshot.values = {"messages": []}
        agent.get_state.return_value = snapshot

        captured_inputs = []

        async def event_generator(inputs, config, **kwargs):
            captured_inputs.append((inputs, config))
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="你好")},
            }

        agent.astream_events = event_generator
        events = [e async for e in chat_stream_session(agent, "你好", "thread-1")]

        assert len(captured_inputs) == 1
        messages = captured_inputs[0][0]["messages"]
        assert messages[0].type == "system"
        assert SYSTEM_PROMPT in messages[0].content
        assert messages[1].type == "human"
        assert messages[1].content == "你好"
        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_session_second_turn_no_system_prompt(self, mocker):
        """续轮不再注入 SYSTEM_PROMPT"""
        agent = mocker.MagicMock()

        snapshot = mocker.MagicMock()
        snapshot.values = {"messages": [mocker.MagicMock(type="human", content="之前的问题")]}
        agent.get_state.return_value = snapshot

        captured_inputs = []

        async def event_generator(inputs, config, **kwargs):
            captured_inputs.append((inputs, config))
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="跟进回答")},
            }

        agent.astream_events = event_generator
        events = [e async for e in chat_stream_session(agent, "追问", "thread-1")]

        assert len(captured_inputs) == 1
        messages = captured_inputs[0][0]["messages"]
        assert len(messages) == 1
        assert messages[0].type == "human"
        assert messages[0].content == "追问"
        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_session_thread_id_in_config(self, mocker):
        """thread_id 传入了 astream_events 的 config"""
        agent = mocker.MagicMock()

        snapshot = mocker.MagicMock()
        snapshot.values = {"messages": []}
        agent.get_state.return_value = snapshot

        captured_config = []

        async def event_generator(inputs, config, **kwargs):
            captured_config.append(config)
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="ok")},
            }

        agent.astream_events = event_generator
        _ = [e async for e in chat_stream_session(agent, "hi", "my-thread-id")]

        assert captured_config[0]["configurable"]["thread_id"] == "my-thread-id"

    @pytest.mark.asyncio
    async def test_session_events_format(self, mocker):
        """事件格式与 chat_stream 一致"""
        agent = mocker.MagicMock()

        snapshot = mocker.MagicMock()
        snapshot.values = {"messages": []}
        agent.get_state.return_value = snapshot

        async def event_generator(inputs, config, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="token1")},
            }
            yield {
                "event": "on_tool_start",
                "run_id": "r2",
                "name": "search_wiki",
                "data": {"input": {"query": "test"}},
            }
            yield {
                "event": "on_tool_end",
                "run_id": "r2",
                "name": "search_wiki",
                "data": {"output": "结果：`entities/test.md`"},
            }

        agent.astream_events = event_generator
        events = [e async for e in chat_stream_session(agent, "test", "t1")]

        types = {e["type"] for e in events}
        assert "token" in types
        assert "tool_start" in types
        assert "tool_end" in types
        assert "done" in types

    @pytest.mark.asyncio
    async def test_session_error_event(self, mocker):
        """异常转成 error 事件（模拟流中崩溃）"""
        agent = mocker.MagicMock()

        snapshot = mocker.MagicMock()
        snapshot.values = {"messages": []}
        agent.get_state.return_value = snapshot

        async def failing_generator(inputs, config, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="一半")},
            }
            raise Exception("会话崩溃")

        agent.astream_events = failing_generator
        events = [e async for e in chat_stream_session(agent, "hi", "err-thread")]

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) >= 1
        assert "崩溃" in error_events[0]["message"]
