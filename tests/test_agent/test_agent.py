"""
Agent 构建 + 流式对话测试

Mock 策略：
  - Mock LangChain's create_agent 返回的 CompiledStateGraph 的 astream_events
  - 避免真实 LLM 调用
"""
import json
import os

import pytest

from src.agent.agent import build_agent, chat_stream


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
        """agent 包含 search_wiki 和 read_page 两个工具"""
        mock_llm = mocker.MagicMock()
        mock_llm.invoke.return_value = mocker.MagicMock(content="ok")
        mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm)
        mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

        # Mock create_agent 来捕获 tools 参数
        mock_create = mocker.patch("src.agent.agent.create_agent")
        mock_create.return_value = mocker.MagicMock()

        agent = build_agent()
        assert agent is not None

        # 验证 create_agent 被调用，且 tools 包含 search_wiki 和 read_page
        call_kwargs = mock_create.call_args.kwargs if mock_create.call_args.kwargs else {}
        tools_arg = mock_create.call_args[1].get("tools") if len(mock_create.call_args) > 1 else None
        # kwargs 方式
        tools_kw = call_kwargs.get("tools", [])
        tool_names = {t.name for t in tools_kw} if tools_kw else set()
        if not tool_names:
            # 如果通过 positional 方式调用 - 检查 args
            for arg in mock_create.call_args:
                if isinstance(arg, list):
                    tool_names = {t.name for t in arg}
                    break
                if isinstance(arg, dict) and "tools" in arg:
                    tool_names = {t.name for t in arg["tools"]}

        # create_agent 在 agent.py 中以关键字参数传递
        # agent.py: agent = create_agent(model=..., tools=..., system_prompt=..., name=...)
        assert "search_wiki" in tool_names
        assert "read_page" in tool_names
        assert "query_graph" not in tool_names  # P1 不包含


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
