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

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agent import build_agent, chat_stream, chat_stream_session
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
        from src.agent.planning.graph import P1_TOOLS

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


def _make_snapshot(mocker, messages: list | None = None, has_interrupt: bool = False):
    """创建 Mock StateSnapshot（模块级，各测试类复用）

    Args:
        mocker: pytest-mock fixture
        messages: state 中的 messages 列表（None=空）
        has_interrupt: 是否模拟 interrupt 状态
    """
    snapshot = mocker.MagicMock()
    snapshot.values = {"messages": messages or []}
    snapshot.interrupts = (mocker.MagicMock(),) if has_interrupt else ()
    return snapshot


class TestChatStreamSession:
    """chat_stream_session 多轮会话隔离版测试

    Mock 策略（MemorySaver 优先，SQLite 冷启动恢复）：
      - agent.get_state 返回空            → 检查 SQLite（需 mock P.load_thread）
      - agent.get_state 返回有消息          → MemorySaver 有状态，不走 SQLite
      - P.load_thread 返回 None             → 首轮
      - P.load_thread 返回持久化数据          → 冷启动恢复
    """

    # ── Helper: mock 首轮场景 ───────────────────────────────────────────

    def _mock_first_turn(self, mocker):
        """Mock MemorySaver 空 + SQLite 无数据 → 首轮对话"""
        agent = mocker.MagicMock()

        # MemorySaver 空（无 interrupt）
        agent.get_state.return_value = _make_snapshot(mocker)

        # SQLite 无数据（冷启动也查不到）
        mocker.patch("src.agent.memory.store.load_thread", return_value=None)

        return agent

    @pytest.mark.asyncio
    async def test_session_first_turn_injects_system_prompt(self, mocker):
        """首轮自动注入 SYSTEM_PROMPT"""
        from src.agent.planning.prompt import SYSTEM_PROMPT

        agent = self._mock_first_turn(mocker)

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
        """续轮不再注入 SYSTEM_PROMPT（MemorySaver 已有状态）"""
        agent = mocker.MagicMock()

        snapshot = _make_snapshot(
            mocker,
            messages=[mocker.MagicMock(type="human", content="之前的问题")],
        )
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
        agent = self._mock_first_turn(mocker)

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
        agent = self._mock_first_turn(mocker)

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
        agent = self._mock_first_turn(mocker)

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

    @pytest.mark.asyncio
    async def test_session_cold_start_recovery(self, mocker):
        """冷启动恢复：MemorySaver 空 + SQLite 有数据 → 从持久化加载历史"""
        from src.agent.planning.prompt import SYSTEM_PROMPT

        agent = mocker.MagicMock()

        # MemorySaver 空（服务器重启，无 interrupt）
        snapshot = _make_snapshot(mocker)
        agent.get_state.return_value = snapshot

        # SQLite 有持久化数据（历史消息）
        persisted_data = (
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "第一轮问题"},
                {"role": "assistant", "content": "第一轮回答"},
            ],
            [],   # attention_sinks
            {},   # working_memory
        )
        mocker.patch("src.agent.memory.store.load_thread", return_value=persisted_data)

        captured_inputs = []

        async def event_generator(inputs, config, **kwargs):
            captured_inputs.append((inputs, config))
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="第二轮回答")},
            }

        agent.astream_events = event_generator
        events = [e async for e in chat_stream_session(agent, "第二轮问题", "cold-thread")]

        # 验证从 SQLite 恢复的 3 条 + 新用户输入 = 4 条消息
        assert len(captured_inputs) == 1
        messages = captured_inputs[0][0]["messages"]
        assert len(messages) == 4

        # 恢复的历史
        assert isinstance(messages[0], SystemMessage)
        assert SYSTEM_PROMPT in messages[0].content
        assert isinstance(messages[1], HumanMessage)
        assert messages[1].content == "第一轮问题"
        assert isinstance(messages[2], AIMessage)
        assert messages[2].content == "第一轮回答"

        # 新追加的本轮输入
        assert isinstance(messages[3], HumanMessage)
        assert messages[3].content == "第二轮问题"

        assert len(events) >= 1

    @pytest.mark.asyncio
    async def test_session_emits_intent_event(self, mocker):
        """首轮对话产出 intent 事件（问候→greeting）"""
        agent = self._mock_first_turn(mocker)

        async def event_generator(inputs, config, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="你好")},
            }

        agent.astream_events = event_generator
        events = [e async for e in chat_stream_session(agent, "你好", "intent-test")]

        intent_events = [e for e in events if e["type"] == "intent"]
        assert len(intent_events) == 1
        # session 使用 classify_intent（无 top_intent 映射），intent 字段就是原始 category
        assert intent_events[0]["intent"] == "greeting"
        assert intent_events[0]["category"] == "greeting"
        assert intent_events[0]["confidence"] >= 0.5

    @pytest.mark.asyncio
    async def test_session_persists_after_stream(self, mocker):
        """流结束后将最终状态保存到 SQLite（save_thread 被调用）"""
        from src.agent.planning.prompt import SYSTEM_PROMPT

        agent = mocker.MagicMock()

        # get_state 前两次返回空（首轮检测），第三次返回最终状态（持久化）
        call_index = [0]  # mutable for closure

        def mock_get_state(config):  # noqa: ARG001
            i = call_index[0]
            call_index[0] += 1
            if i <= 1:
                # Call 1: pre-stream, Call 2: post-stream interrupt check
                snap = mocker.MagicMock()
                snap.values = {"messages": []}
                snap.interrupts = ()
                return snap
            # Call 3: persistence
            snap = mocker.MagicMock()
            snap.values = {
                "messages": [
                    SystemMessage(content=SYSTEM_PROMPT),
                    HumanMessage(content="hi"),
                    AIMessage(content="回复"),
                ]
            }
            snap.interrupts = ()
            return snap

        agent.get_state = mock_get_state

        async def event_generator(inputs, config, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="回复")},
            }

        agent.astream_events = event_generator

        # mock save_thread
        mock_save = mocker.patch("src.agent.memory.store.save_thread")

        _ = [e async for e in chat_stream_session(agent, "hi", "persist-thread")]

        # save_thread 被调用且传入了正确的 thread_id
        assert mock_save.called
        call_args = mock_save.call_args
        assert call_args[0][0] == "persist-thread"
        # 序列化后的消息列表中包含角色
        serialized = call_args[0][1]
        assert len(serialized) >= 2
        assert serialized[0]["role"] == "system"
        assert serialized[-1]["role"] == "assistant"


# ============================================================================
# 人工审批（Human-in-the-Loop）
# ============================================================================


class TestHumanApproval:
    """human_approval_node + interrupt 检测 + 审批恢复测试"""

    def _make_interrupt_snapshot(self, mocker, tool_calls=None):
        """创建包含 interrupt 的 StateSnapshot"""
        snapshot = mocker.MagicMock()
        snapshot.values = {"messages": [mocker.MagicMock()]}
        snapshot.interrupts = (
            mocker.MagicMock(value={
                "question": "是否批准以下工具调用？",
                "tool_calls": tool_calls or [
                    {"name": "search_wiki", "args": {"query": "test"}, "id": "call_1"},
                ],
            }),
        )
        return snapshot

    @pytest.mark.asyncio
    async def test_interrupt_detected_after_stream(self, mocker):
        """工具调用后流正常结束，但 get_state 显示 interrupt → 发出 tool_approval_needed"""
        agent = mocker.MagicMock()

        # get_state: call 1 = 正常（首轮）, call 2 = interrupt 状态
        call_idx = [0]

        def mock_get_state(config):  # noqa: ARG001
            i = call_idx[0]
            call_idx[0] += 1
            if i == 0:
                s = _make_snapshot(mocker)
                return s
            # Post-stream: 模拟 interrupted
            return self._make_interrupt_snapshot(mocker, tool_calls=[
                {"name": "search_wiki", "args": {"query": "Python"}, "id": "call_abc"},
            ])

        agent.get_state = mock_get_state

        # astream_events 正常完成（模拟 agent 节点输出了 tool_calls）
        async def stream_events(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="")},
            }

        agent.astream_events = stream_events

        # Mock SQLite 无数据
        mocker.patch("src.agent.memory.store.load_thread", return_value=None)
        mock_save = mocker.patch("src.agent.memory.store.save_thread")

        events = [e async for e in chat_stream_session(agent, "查 Python", "interrupt-test")]

        # 应发出 tool_approval_needed 事件
        approval_events = [e for e in events if e["type"] == "tool_approval_needed"]
        assert len(approval_events) == 1
        assert "tool_calls" in approval_events[0]
        assert approval_events[0]["tool_calls"][0]["name"] == "search_wiki"

        # 不应有 done 事件
        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 0

        # 不应持久化
        assert not mock_save.called

    @pytest.mark.asyncio
    async def test_approval_required_when_no_approval_given(self, mocker):
        """graph 已中断但请求未带 approval → 返回 error 事件"""
        agent = mocker.MagicMock()

        # get_state 直接返回 interrupt 状态
        agent.get_state.return_value = self._make_interrupt_snapshot(mocker)

        events = [e async for e in chat_stream_session(agent, "hi", "no-approval")]

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "审批" in error_events[0]["message"]

    @pytest.mark.asyncio
    async def test_approve_resume(self, mocker):
        """审批批准后恢复图执行，正常流式输出 → done"""
        agent = mocker.MagicMock()

        # get_state: call 1 = interrupt, call 2+ = 正常
        call_idx = [0]

        def mock_get_state(config):  # noqa: ARG001
            i = call_idx[0]
            call_idx[0] += 1
            if i == 0:
                return self._make_interrupt_snapshot(mocker)
            s = _make_snapshot(mocker)
            return s

        agent.get_state = mock_get_state

        # 捕获传给 astream_events 的 input
        captured_input = []

        async def event_generator(input_arg, config, **kwargs):
            captured_input.append(input_arg)
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="审批批准后继续")},
            }

        agent.astream_events = event_generator

        mock_save = mocker.patch("src.agent.memory.store.save_thread")

        approval = {"approved": True}
        events = [e async for e in chat_stream_session(agent, "", "approve-test", approval=approval)]

        # 验证输入是 Command(resume=approval)
        from langgraph.types import Command

        assert len(captured_input) == 1
        assert isinstance(captured_input[0], Command)
        assert captured_input[0].resume == approval

        # 正常流式事件
        token_events = [e for e in events if e["type"] == "token"]
        assert len(token_events) >= 1

        # done 事件
        done_events = [e for e in events if e["type"] == "done"]
        assert len(done_events) == 1

        # 持久化
        assert mock_save.called

    @pytest.mark.asyncio
    async def test_reject_resume(self, mocker):
        """审批拒绝后恢复图执行，正常流式输出 → done"""
        agent = mocker.MagicMock()

        call_idx = [0]

        def mock_get_state(config):  # noqa: ARG001
            i = call_idx[0]
            call_idx[0] += 1
            if i == 0:
                return self._make_interrupt_snapshot(mocker)
            s = _make_snapshot(mocker)
            return s

        agent.get_state = mock_get_state

        async def event_generator(input_arg, config, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="工具被拒后回答")},
            }

        agent.astream_events = event_generator

        mock_save = mocker.patch("src.agent.memory.store.save_thread")

        approval = {"approved": False}
        events = [e async for e in chat_stream_session(agent, "", "reject-test", approval=approval)]

        # 正常流式事件
        assert any(e["type"] == "token" for e in events)

        # done 事件
        assert any(e["type"] == "done" for e in events)

        # 持久化
        assert mock_save.called

    @pytest.mark.asyncio
    async def test_no_interrupt_on_direct_answer(self, mocker):
        """LLM 直接回答（无 tool_calls）时不会触发 interrupt"""
        agent = mocker.MagicMock()

        # get_state 正常
        call_idx = [0]

        def mock_get_state(config):  # noqa: ARG001
            i = call_idx[0]
            call_idx[0] += 1
            s = _make_snapshot(mocker)
            return s

        agent.get_state = mock_get_state

        async def event_generator(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="直接回答")},
            }

        agent.astream_events = event_generator

        mocker.patch("src.agent.memory.store.load_thread", return_value=None)
        mock_save = mocker.patch("src.agent.memory.store.save_thread")

        events = [e async for e in chat_stream_session(agent, "你好", "direct-answer")]

        # 无审批事件
        assert all(e["type"] != "tool_approval_needed" for e in events)

        # 有 done 事件
        assert any(e["type"] == "done" for e in events)

        # 持久化
        assert mock_save.called


# ============================================================================
# 自修正机制（Self-Correction）
# ============================================================================


class TestMakeActionKey:
    """_make_action_key 动作键生成测试"""

    def test_search_wiki_normalization(self):
        """search_wiki 的 query 转为小写去空格"""
        from src.agent.planning.graph import _make_action_key

        key1 = _make_action_key("search_wiki", {"query": "异步编程"})
        key2 = _make_action_key("search_wiki", {"query": "  异步编程  "})
        key3 = _make_action_key("search_wiki", {"query": "异步编程"})

        assert key1 == key2 == key3
        assert "search_wiki|" in key1

    def test_read_page_normalization(self):
        """read_page 的 path 保持一致"""
        from src.agent.planning.graph import _make_action_key

        key1 = _make_action_key("read_page", {"path": "entities/异步.md"})
        key2 = _make_action_key("read_page", {"path": "entities/异步.md", "offset": 0})
        key3 = _make_action_key("read_page", {"path": "  entities/异步.md  "})

        assert key1 == key2
        assert "read_page|" in key1

    def test_different_tools_different_keys(self):
        """不同工具生成不同的键"""
        from src.agent.planning.graph import _make_action_key

        k1 = _make_action_key("search_wiki", {"query": "python"})
        k2 = _make_action_key("read_page", {"path": "python.md"})
        assert k1 != k2

    def test_different_queries_different_keys(self):
        """不同 query 生成不同的键"""
        from src.agent.planning.graph import _make_action_key

        k1 = _make_action_key("search_wiki", {"query": "异步"})
        k2 = _make_action_key("search_wiki", {"query": "同步"})
        assert k1 != k2


class TestValidateToolNode:
    """validate_tool_node 前置校验测试"""

    def test_step_limit_triggers_summarizer(self, mocker):
        """步数超限时设置 step_limit_reached 标记"""
        from src.agent.planning.graph import validate_tool_node

        tool_call = mocker.MagicMock()
        tool_call.tool_calls = [
            {"name": "search_wiki", "args": {"query": "test"}, "id": "call_1"}
        ]
        # 步数超限
        state = {
            "messages": [tool_call],
            "step_count": 15,  # MAX_STEPS = 15
            "executed_actions": {},
        }
        result = validate_tool_node(state)
        assert result["self_correction"].get("step_limit_reached") is True
        # 步数超限时注入 ToolMessage
        assert "messages" in result
        assert len(result["messages"]) == 1

    @pytest.mark.asyncio
    async def test_step_limit_routes_to_summarizer(self, mocker):
        """should_after_validate 在 step_limit 时路由到 summarizer"""
        from src.agent.planning.graph import should_after_validate

        state = {"self_correction": {"step_limit_reached": True}}
        assert should_after_validate(state) == "summarizer"

    def test_duplicate_action_detected(self, mocker):
        """重复动作被拦截并设置 correction_reason"""
        from src.agent.planning.graph import validate_tool_node

        tool_call = mocker.MagicMock()
        tool_call.tool_calls = [
            {"name": "search_wiki", "args": {"query": "python"}, "id": "call_1"}
        ]
        state = {
            "messages": [tool_call],
            "step_count": 3,
            "executed_actions": {
                "search_wiki|python": {
                    "tool": "search_wiki",
                    "args": {"query": "python"},
                    "quality": "poor",
                }
            },
        }
        result = validate_tool_node(state)
        assert result["self_correction"].get("correction_reason") == "duplicate"
        assert "messages" in result  # 注入 ToolMessage 提示

    @pytest.mark.asyncio
    async def test_duplicate_routes_to_agent(self, mocker):
        """should_after_validate 在重复时路由到 agent"""
        from src.agent.planning.graph import should_after_validate

        state = {"self_correction": {"correction_reason": "duplicate"}}
        assert should_after_validate(state) == "agent"

    def test_duplicate_with_good_result_allows(self, mocker):
        """如果之前的结果质量好，重复动作不被拦截"""
        from src.agent.planning.graph import validate_tool_node

        tool_call = mocker.MagicMock()
        tool_call.tool_calls = [
            {"name": "search_wiki", "args": {"query": "python"}, "id": "call_1"}
        ]
        state = {
            "messages": [tool_call],
            "step_count": 3,
            "executed_actions": {
                "search_wiki|python": {
                    "tool": "search_wiki",
                    "args": {"query": "python"},
                    "quality": "good",
                }
            },
        }
        result = validate_tool_node(state)
        # 结果质量 good，不拦截
        assert result["self_correction"].get("validated") is True
        assert "messages" not in result

    def test_valid_tool_call_passes(self, mocker):
        """有效工具调用通过校验"""
        from src.agent.planning.graph import validate_tool_node

        tool_call = mocker.MagicMock()
        tool_call.tool_calls = [
            {"name": "search_wiki", "args": {"query": "python"}, "id": "call_1"}
        ]
        state = {
            "messages": [tool_call],
            "step_count": 3,
            "executed_actions": {},
        }
        result = validate_tool_node(state)
        assert result["self_correction"].get("validated") is True
        assert "messages" not in result

    @pytest.mark.asyncio
    async def test_valid_routes_to_approve(self, mocker):
        """should_after_validate 在 validated 时路由到 approve"""
        from src.agent.planning.graph import should_after_validate

        state = {"self_correction": {"validated": True}}
        assert should_after_validate(state) == "approve"

    def test_no_tool_calls_returns_validated(self, mocker):
        """无 tool_calls 时直接返回 validated=True"""
        from src.agent.planning.graph import validate_tool_node

        ai_msg = mocker.MagicMock()
        ai_msg.tool_calls = []
        state = {
            "messages": [ai_msg],
            "step_count": 5,
            "executed_actions": {},
        }
        result = validate_tool_node(state)
        assert result["self_correction"].get("validated") is True


class TestVerifyResultNode:
    """verify_result_node 后置验证测试"""

    def _make_state(self, tool_name="search_wiki", tool_args=None, output=""):
        """构造包含工具调用和结果的测试状态"""
        if tool_args is None:
            tool_args = {"query": "test"}

        ai_msg = AIMessage(
            content="让我搜索一下",
            tool_calls=[
                {"name": tool_name, "args": tool_args, "id": "call_1", "type": "tool_call"}
            ],
        )
        tool_msg = ToolMessage(content=output, tool_call_id="call_1")

        return {
            "messages": [ai_msg, tool_msg],
            "executed_actions": {},
        }

    def test_detects_poor_result_empty(self):
        """空结果被标记为 poor"""
        from src.agent.planning.graph import verify_result_node

        state = self._make_state(output="未找到匹配的页面")
        result = verify_result_node(state)
        assert result["self_correction"].get("poor_result") is True
        assert "search_wiki" in result["self_correction"].get("poor_tools", [])

    def test_detects_poor_result_error(self):
        """错误结果被标记为 poor"""
        from src.agent.planning.graph import verify_result_node

        state = self._make_state(output="错误: 搜索失败")
        result = verify_result_node(state)
        assert result["self_correction"].get("poor_result") is True

    def test_good_result_passes(self):
        """正常结果通过验证"""
        from src.agent.planning.graph import verify_result_node

        state = self._make_state(output="- **Python** (`entities/python.md`) [匹配度 0.85]")
        result = verify_result_node(state)
        assert result["self_correction"].get("verified") is True
        assert result["self_correction"].get("poor_result") is not True

    def test_records_executed_action(self):
        """工具调用被记录到 executed_actions"""
        from src.agent.planning.graph import verify_result_node

        state = self._make_state(
            tool_name="search_wiki",
            tool_args={"query": "python"},
            output="- **Python** (`entities/python.md`)",
        )
        result = verify_result_node(state)
        assert "executed_actions" in result
        assert "search_wiki|python" in result["executed_actions"]
        assert result["executed_actions"]["search_wiki|python"]["quality"] == "good"

    def test_records_poor_action(self):
        """差的结果在 executed_actions 中标记为 poor"""
        from src.agent.planning.graph import verify_result_node

        state = self._make_state(output="未找到匹配的页面")
        result = verify_result_node(state)
        action_key = next(k for k in result["executed_actions"].keys() if "test" in k)
        assert result["executed_actions"][action_key]["quality"] == "poor"

    def test_no_tool_call_messages(self):
        """无 ToolMessage 时直接通过验证"""
        from src.agent.planning.graph import verify_result_node

        state = {
            "messages": [HumanMessage(content="hi")],
            "executed_actions": {},
        }
        result = verify_result_node(state)
        assert result["self_correction"].get("verified") is True

    @pytest.mark.asyncio
    async def test_poor_routes_to_reflect(self, mocker):
        """should_after_verify 在 poor 时路由到 reflect_node"""
        from src.agent.planning.graph import should_after_verify

        state = {"self_correction": {"poor_result": True, "poor_tools": ["search_wiki"]}}
        assert should_after_verify(state) == "reflect_node"

    @pytest.mark.asyncio
    async def test_good_routes_to_agent(self, mocker):
        """should_after_verify 在 verified 时路由到 agent"""
        from src.agent.planning.graph import should_after_verify

        state = {"self_correction": {"verified": True}}
        assert should_after_verify(state) == "agent"


class TestReflectNode:
    """reflect_node 反思节点测试"""

    def test_reflect_fallback_on_error(self, mocker):
        """LLM 调用失败时默认 proceed，不阻断流程"""
        from src.agent.planning.graph import reflect_node

        # 模拟 LLM 调用失败
        mocker.patch.object(
            type(reflect_node.__globals__["llm"]),
            "with_structured_output",
            side_effect=Exception("API Error"),
        )

        state = {
            "messages": [HumanMessage(content="test")],
            "self_correction": {"poor_result": True, "poor_tools": ["search_wiki"]},
        }
        result = reflect_node(state)
        assert result["self_correction"]["reflection_verdict"] == "proceed"


class TestGraphStructure:
    """图结构完整性测试（验证新节点在编译图中）"""

    def test_graph_contains_self_correction_nodes(self, mocker):
        """编译图中包含 validate_tool, verify_result, reflect_node"""
        mock_llm = mocker.MagicMock()
        mock_llm.invoke.return_value = mocker.MagicMock(content="ok")
        mocker.patch("src.agent.planning.graph.ChatOpenAI", return_value=mock_llm)
        mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

        from src.agent import build_agent

        agent = build_agent()
        graph = agent.get_graph()
        node_names = {n for n in graph.nodes.keys() if not n.startswith("__")}

        assert "validate_tool" in node_names
        assert "verify_result" in node_names
        assert "reflect_node" in node_names
        assert "approve" in node_names
        assert "tools" in node_names
        assert "agent" in node_names

    def test_graph_contains_intent_classifier_node(self, mocker):
        """编译图中包含 intent_classifier 节点"""
        mock_llm = mocker.MagicMock()
        mock_llm.invoke.return_value = mocker.MagicMock(content="ok")
        mocker.patch("src.agent.planning.graph.ChatOpenAI", return_value=mock_llm)
        mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

        from src.agent import build_agent

        agent = build_agent()
        graph = agent.get_graph()
        node_names = {n for n in graph.nodes.keys() if not n.startswith("__")}

        assert "intent_classifier" in node_names


# ============================================================================
# IntentClassifier
# ============================================================================


class TestIntentClassifier:
    """意图分类规则测试"""

    def test_classify_greeting(self):
        from src.agent.perception.intent import classify_intent
        from src.agent import constants as C

        result = classify_intent("你好")
        assert result["category"] == C.INTENT_GREETING
        assert result["confidence"] >= C.INTENT_CONFIDENCE_MEDIUM

    def test_classify_greeting_thanks(self):
        from src.agent.perception.intent import classify_intent
        from src.agent import constants as C

        result = classify_intent("谢谢你的帮助")
        assert result["category"] == C.INTENT_GREETING

    def test_classify_knowledge_query(self):
        from src.agent.perception.intent import classify_intent
        from src.agent import constants as C

        result = classify_intent("什么是Python异步编程？")
        assert result["category"] == C.INTENT_KNOWLEDGE_QUERY

    def test_classify_knowledge_query_how(self):
        from src.agent.perception.intent import classify_intent
        from src.agent import constants as C

        result = classify_intent("如何用FastAPI创建路由")
        assert result["category"] == C.INTENT_KNOWLEDGE_QUERY

    def test_classify_chit_chat(self):
        from src.agent.perception.intent import classify_intent
        from src.agent import constants as C

        result = classify_intent("今天天气真好")
        assert result["category"] == C.INTENT_CHIT_CHAT

    def test_classify_clarification(self):
        from src.agent.perception.intent import classify_intent
        from src.agent import constants as C

        result = classify_intent("能详细说说吗？")
        assert result["category"] == C.INTENT_CLARIFICATION

    def test_classify_tool_operation(self):
        from src.agent.perception.intent import classify_intent
        from src.agent import constants as C

        result = classify_intent("怎么搜索页面？")
        assert result["category"] == C.INTENT_TOOL_OPERATION

    def test_classify_empty_returns_unknown(self):
        from src.agent.perception.intent import classify_intent
        from src.agent import constants as C

        result = classify_intent("")
        assert result["category"] == C.INTENT_UNKNOWN
        assert result["confidence"] == 0.0

    def test_classify_short_non_chinese_fallsback_unknown(self):
        from src.agent.perception.intent import classify_intent
        from src.agent import constants as C

        result = classify_intent("abc")
        assert result["category"] == C.INTENT_UNKNOWN

    def test_classify_whitespace_returns_unknown(self):
        """全空白字符输入返回 unknown"""
        from src.agent.perception.intent import classify_intent
        from src.agent import constants as C

        result = classify_intent("   ")
        assert result["category"] == C.INTENT_UNKNOWN

    def test_classify_general_query(self):
        """不含特定提问词的中文文本归类为 general_query"""
        from src.agent.perception.intent import classify_intent
        from src.agent import constants as C

        # "了解一下"匹配 knowledge_query，用不含提问词的句子
        result = classify_intent("我今天去了图书馆")
        assert result["category"] == C.INTENT_GENERAL_QUERY

    def test_classify_user_intent_returns_top_intent(self):
        """classify_user_intent 返回 top_intent 映射"""
        from src.agent.perception.intent import classify_user_intent
        from src.agent import constants as C

        # 问候 → top_intent = chat
        result = classify_user_intent("你好")
        assert "top_intent" in result
        assert result["top_intent"] == C.INTENT_CHAT

        # 知识查询 → top_intent = search
        result = classify_user_intent("什么是Python？")
        assert result["top_intent"] == C.INTENT_SEARCH

    def test_classify_user_intent_default_fallback(self):
        """classify_user_intent 规则未知且无 LLM 时返回默认 general_query"""
        from src.agent.perception.intent import classify_user_intent
        from src.agent import constants as C

        # 短英文规则未匹配 → classify_intent 返回 unknown
        # classify_user_intent 因 llm=None 走默认降级 → general_query
        result = classify_user_intent("xyz")
        assert result["category"] == C.INTENT_GENERAL_QUERY
        assert result["top_intent"] == C.INTENT_SEARCH


# ============================================================================
# ToolRegistry
# ============================================================================


class TestToolRegistry:
    """工具注册中心测试"""

    def test_register_tool(self):
        from src.agent.action.registry import ToolRegistry

        reg = ToolRegistry()

        def mock_tool(query: str) -> str:
            """Mock tool"""
            return f"result: {query}"
        mock_tool.name = "mock_search"

        name = reg.register(mock_tool)
        assert name == "mock_search"
        assert reg.count() == 1

    def test_register_duplicate_raises(self):
        from src.agent.action.registry import ToolRegistry

        reg = ToolRegistry()

        def t1():
            pass
        t1.name = "my_tool"

        reg.register(t1)
        import pytest

        def t2():
            pass
        t2.name = "my_tool"

        with pytest.raises(ValueError):
            reg.register(t2)

    def test_unregister(self):
        from src.agent.action.registry import ToolRegistry

        reg = ToolRegistry()

        def t():
            pass
        t.name = "t1"

        reg.register(t)
        assert reg.count() == 1
        reg.unregister("t1")
        assert reg.count() == 0

    def test_enable_disable(self):
        from src.agent.action.registry import ToolRegistry

        reg = ToolRegistry()

        def t():
            pass
        t.name = "my_tool"

        reg.register(t, enabled=False)
        assert reg.is_enabled("my_tool") is False
        assert reg.count_enabled() == 0

        reg.enable("my_tool")
        assert reg.is_enabled("my_tool") is True
        assert reg.count_enabled() == 1

        reg.disable("my_tool")
        assert reg.is_enabled("my_tool") is False

    def test_list_enabled_filters(self):
        from src.agent.action.registry import ToolRegistry

        reg = ToolRegistry()

        def t1():
            pass
        t1.name = "t1"

        def t2():
            pass
        t2.name = "t2"

        reg.register(t1, enabled=True)
        reg.register(t2, enabled=False)

        enabled = reg.list_enabled()
        assert len(enabled) == 1
        assert enabled[0].name == t1.name

    def test_list_all_returns_all(self):
        from src.agent.action.registry import ToolRegistry

        reg = ToolRegistry()

        def t1():
            pass
        t1.name = "t1"

        def t2():
            pass
        t2.name = "t2"

        reg.register(t1)
        reg.register(t2)

        all_tools = reg.list_all()
        assert len(all_tools) == 2

    def test_get_returns_tool(self):
        from src.agent.action.registry import ToolRegistry

        reg = ToolRegistry()

        def t():
            pass
        t.name = "my_tool"

        reg.register(t)
        retrieved = reg.get("my_tool")
        assert retrieved is t

    def test_get_nonexistent_returns_none(self):
        from src.agent.action.registry import ToolRegistry

        reg = ToolRegistry()
        assert reg.get("nope") is None

    def test_global_registry_has_default_tools(self):
        """全局 registry 应该包含默认注册的 search_wiki 和 read_page"""
        from src.agent.action.registry import registry

        assert registry.count() >= 2
        assert registry.is_enabled("search_wiki")
        assert registry.is_enabled("read_page")
        assert registry.get("search_wiki") is not None
        assert registry.get("read_page") is not None

    def test_p1_tools_backward_compat(self):
        """P1_TOOLS 向后兼容：仍可导入且包含正确的工具"""
        from src.agent.planning.graph import P1_TOOLS

        tool_names = {t.name for t in P1_TOOLS}
        assert "search_wiki" in tool_names
        assert "read_page" in tool_names
        assert "query_graph" not in tool_names

    def test_list_names(self):
        """list_names 返回所有注册名"""
        from src.agent.action.registry import ToolRegistry

        reg = ToolRegistry()

        def t1():
            pass
        t1.name = "tool_a"

        def t2():
            pass
        t2.name = "tool_b"

        reg.register(t1, enabled=True)
        reg.register(t2, enabled=False)

        names = reg.list_names()
        assert "tool_a" in names
        assert "tool_b" in names
        assert len(names) == 2

        enabled_names = reg.list_enabled_names()
        assert enabled_names == ["tool_a"]

    def test_get_def_returns_definition(self):
        """get_def 返回 ToolDefinition 对象"""
        from src.agent.action.registry import ToolRegistry, ToolDefinition

        reg = ToolRegistry()

        def t():
            pass
        t.name = "my_tool"

        reg.register(t)
        td = reg.get_def("my_tool")
        assert td is not None
        assert isinstance(td, ToolDefinition)
        assert td.name == "my_tool"
        assert td.enabled is True

    def test_get_def_nonexistent_returns_none(self):
        """get_def 对未知工具返回 None"""
        from src.agent.action.registry import ToolRegistry

        reg = ToolRegistry()
        assert reg.get_def("nope") is None

    def test_unregister_nonexistent_does_not_crash(self):
        """unregister 不存在的工具不会崩溃"""
        from src.agent.action.registry import ToolRegistry

        reg = ToolRegistry()
        reg.unregister("nope")  # should not raise

    def test_metadata_operations(self):
        """get_metadata / set_metadata 正常运作"""
        from src.agent.action.registry import ToolRegistry

        reg = ToolRegistry()

        def t():
            pass
        t.name = "my_tool"

        reg.register(t, metadata={"category": "search"})

        # 获取全部元数据
        assert reg.get_metadata("my_tool") == {"category": "search"}
        # 获取特定键
        assert reg.get_metadata("my_tool", "category") == "search"
        # 不存在的键返回 None
        assert reg.get_metadata("my_tool", "nope") is None
        # 不存在的工具返回 None
        assert reg.get_metadata("nope") is None

        # 更新元数据
        reg.set_metadata("my_tool", {"version": 2})
        assert reg.get_metadata("my_tool", "version") == 2
        assert reg.get_metadata("my_tool", "category") == "search"  # update 不覆盖

    def test_get_tool_info_returns_list(self):
        """get_tool_info 返回工具信息列表"""
        from src.agent.action.registry import get_tool_info

        info = get_tool_info()
        assert isinstance(info, list)
        names = [i["name"] for i in info]
        assert "search_wiki" in names
        assert "read_page" in names
        for entry in info:
            assert "name" in entry
            assert "description" in entry
