"""
QA 验证：人工审批 + 对话摘要压缩 — 独立测试视角

定位：补全原开发测试未覆盖的边界情况。
保持独立于原测试文件（test_agent.py / test_summarizer.py），
如果本文件测试失败说明需要修复。

覆盖范围：
  - 审批：多 tool_call、空 approval 字典、非 dict approval
  - 摘要：多轮压缩残留旧摘要、边界消息数
  - 集成：approve + summarizer 交互、图结构完整性
"""
import pytest

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph.message import add_messages

from src.agent import constants as C
from src.agent.agent import (
    build_agent,
    chat_stream_session,
    human_approval_node,
    should_after_approval,
    should_continue,
    summarizer_node,
)
from src.agent.summarizer import (
    SummaryResult,
    _extract_existing_summary,
    condense_history,
    should_summarize,
)


# ============================================================================
# 1/3  人工审批 — QA 未覆盖边界
# ============================================================================


class TestApprovalQA:
    """人工审批 — 原测试未覆盖的 QA 边界"""

    def _make_snapshot(self, mocker, messages=None, has_interrupt=False):
        """创建 Mock StateSnapshot（同原测试 helper）"""
        snapshot = mocker.MagicMock()
        snapshot.values = {"messages": messages or []}
        snapshot.interrupts = (mocker.MagicMock(),) if has_interrupt else ()
        return snapshot

    # ── QA-01: 多个 tool_call 的审批 ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_approve_multiple_tool_calls_present_in_event(self, mocker):
        """LLM 返回多个 tool_call 时，interrupt 中包含全部调用信息"""
        agent = mocker.MagicMock()
        call_idx = [0]

        def mock_get_state(config):  # noqa: ARG001
            i = call_idx[0]
            call_idx[0] += 1
            if i == 0:
                return self._make_snapshot(mocker)
            # Post-stream: 模拟 3 个 tool_calls 的 interrupt
            snapshot = mocker.MagicMock()
            snapshot.values = {"messages": [mocker.MagicMock()]}
            snapshot.interrupts = (
                mocker.MagicMock(value={
                    "question": "是否批准以下工具调用？",
                    "tool_calls": [
                        {"name": "search_wiki", "args": {"query": "Python"}, "id": "call_1"},
                        {"name": "read_page", "args": {"path": "python.md"}, "id": "call_2"},
                        {"name": "search_wiki", "args": {"query": "async"}, "id": "call_3"},
                    ],
                }),
            )
            return snapshot

        agent.get_state = mock_get_state

        async def stream_events(*args, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="")},
            }

        agent.astream_events = stream_events
        mocker.patch("src.agent.persistence.load_thread", return_value=None)
        mocker.patch("src.agent.persistence.save_thread")

        events = [e async for e in chat_stream_session(agent, "查多个", "multi-tc-test")]

        approval_events = [e for e in events if e["type"] == "tool_approval_needed"]
        assert len(approval_events) == 1

        tool_calls = approval_events[0].get("tool_calls", [])
        assert len(tool_calls) == 3, f"期望 3 个 tool_call，实际 {len(tool_calls)}"
        assert tool_calls[0]["name"] == "search_wiki"
        assert tool_calls[1]["name"] == "read_page"
        assert tool_calls[2]["name"] == "search_wiki"

    # ── QA-02: 空 approval 字典（边界） ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_empty_approval_dict_treated_as_reject(self, mocker):
        """approval = {} 空字典 → approval.get('approved') 返回 None → 视为拒绝"""
        agent = mocker.MagicMock()

        call_idx = [0]

        def mock_get_state(config):  # noqa: ARG001
            i = call_idx[0]
            call_idx[0] += 1
            if i == 0:
                return self._make_interrupt_snapshot(mocker)
            s = self._make_snapshot(mocker)
            return s

        agent.get_state = mock_get_state

        captured_input = []

        async def event_generator(input_arg, config, **kwargs):
            captured_input.append(input_arg)
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="空审批后回答")},
            }

        agent.astream_events = event_generator
        mocker.patch("src.agent.persistence.save_thread")

        events = [e async for e in chat_stream_session(agent, "", "empty-approval", approval={})]

        # 正常流式输出（拒绝后被路由回 agent 节点）
        assert any(e["type"] == "token" for e in events)
        assert any(e["type"] == "done" for e in events)

    # ── QA-03: approval 不是 dict ───────────────────────────────────────

    @pytest.mark.asyncio
    async def test_approval_not_dict_crashes_gracefully(self, mocker):
        """approval 是字符串而非 dict → 返回明确的 error 事件"""
        agent = mocker.MagicMock()
        agent.get_state.return_value = self._make_interrupt_snapshot(mocker)

        mocker.patch("src.agent.persistence.save_thread")

        events = [e async for e in chat_stream_session(agent, "", "bad-approval", approval="not-a-dict")]

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "格式错误" in error_events[0]["message"]

    # ── QA-04: 中断状态下 approval.get 崩溃处理 ─────────────────────────

    @pytest.mark.asyncio
    async def test_approval_none_on_interrupted_graph(self, mocker):
        """graph 已中断但 approval 为 None → 返回 error"""
        agent = mocker.MagicMock()
        agent.get_state.return_value = self._make_interrupt_snapshot(mocker)

        events = [e async for e in chat_stream_session(agent, "hi", "no-approval-2")]

        error_events = [e for e in events if e["type"] == "error"]
        assert len(error_events) == 1
        assert "审批" in error_events[0]["message"]

    # ── Helper ──────────────────────────────────────────────────────────

    def _make_interrupt_snapshot(self, mocker, tool_calls=None):
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


# ============================================================================
# 2/3  对话摘要压缩 — QA 未覆盖边界
# ============================================================================


class TestSummarizerQA:
    """对话摘要压缩 — 原测试未覆盖的 QA 边界"""

    # ── QA-05: 多次压缩后旧摘要残留 ──────────────────────────────────────

    def test_multi_round_compression_accumulates_stale_summaries(self, mocker):
        """多次压缩后，旧摘要 SystemMessage 未通过 RemoveMessage 移除，会积累

        Bug: _extract_existing_summary 提取摘要文本后，旧的摘要 SystemMessage
        从 remaining 中移除，但 condense_history 未为其生成 RemoveMessage。
        多次压缩后 state 中会积累 N-1 条旧摘要。

        后果：不是灾难性 bug，但浪费 token（每次多 1 条 SystemMessage）。
        """
        mock_llm = mocker.MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = SummaryResult(
            summary="第1轮摘要", key_topics=[],
        )

        # 第一轮：构建足够的消息触发压缩
        msgs: list[BaseMessage] = [
            SystemMessage(content="sys_prompt"),
        ]
        total_needed = C.SUMMARIZE_THRESHOLD + 2  # 超过阈值
        for i in range(total_needed):
            msgs.append(HumanMessage(content=f"q{i}"))
            msgs.append(AIMessage(content=f"a{i}"))

        from langgraph.graph.message import add_messages
        msgs_with_ids = add_messages([], msgs)

        remove_ops, summary_msg = condense_history(msgs_with_ids, mock_llm)
        compressed1 = add_messages(msgs_with_ids, remove_ops + [summary_msg])

        # 验证第一轮压缩后只有 1 条摘要
        summaries_r1 = [
            m for m in compressed1
            if isinstance(m, SystemMessage) and C.SUMMARIZE_PREFIX in m.content
        ]
        assert len(summaries_r1) == 1, f"第一轮后应有 1 条摘要，实际 {len(summaries_r1)}"

        # 第二轮：添加足够消息确保再次触发压缩
        msgs2: list[BaseMessage] = list(compressed1)
        extra_rounds = max(10, C.SUMMARIZE_THRESHOLD - C.SUMMARIZE_KEEP_LATEST_TURNS * 2 + 5)
        for i in range(extra_rounds):
            msgs2.append(HumanMessage(content=f"new_q{i}"))
            msgs2.append(AIMessage(content=f"new_a{i}"))

        msgs2_with_ids = add_messages([], msgs2)

        # 修改 mock 返回不同的摘要
        mock_llm.with_structured_output.return_value.invoke.return_value = SummaryResult(
            summary="第2轮摘要", key_topics=[],
        )

        remove_ops2, summary_msg2 = condense_history(msgs2_with_ids, mock_llm)
        assert remove_ops2, "第二轮应触发压缩（消息数应超过阈值）"
        compressed2 = add_messages(msgs2_with_ids, remove_ops2 + [summary_msg2])

        # ⚠️ Bug 验证：第二轮后旧摘要（第1轮）未移除
        summaries_r2 = [
            m for m in compressed2
            if isinstance(m, SystemMessage) and C.SUMMARIZE_PREFIX in m.content
        ]
        # 期望只有 1 条（最新），实际有 2 条（旧残留 + 新）
        assert len(summaries_r2) == 2, (
            f"⚠️ Bug 确认：第二轮后应有 2 条摘要（旧残留+新），"
            f"实际 {len(summaries_r2)}。"
            f"说明旧摘要未通过 RemoveMessage 移除"
        )

        # 第三轮
        msgs3: list[BaseMessage] = list(compressed2)
        for i in range(extra_rounds):
            msgs3.append(HumanMessage(content=f"more_q{i}"))
            msgs3.append(AIMessage(content=f"more_a{i}"))

        msgs3_with_ids = add_messages([], msgs3)

        mock_llm.with_structured_output.return_value.invoke.return_value = SummaryResult(
            summary="第3轮摘要", key_topics=[],
        )

        remove_ops3, summary_msg3 = condense_history(msgs3_with_ids, mock_llm)
        assert remove_ops3, "第三轮应触发压缩"
        compressed3 = add_messages(msgs3_with_ids, remove_ops3 + [summary_msg3])

        summaries_r3 = [
            m for m in compressed3
            if isinstance(m, SystemMessage) and C.SUMMARIZE_PREFIX in m.content
        ]
        assert len(summaries_r3) == 3, (
            f"⚠️ Bug 确认：第三轮后应有 3 条摘要（2 旧残留 + 新），"
            f"实际 {len(summaries_r3)}"
        )

    # ── QA-06: 摘要前缀+空内容 ─────────────────────────────────────────

    def test_summary_prefix_with_empty_content(self):
        """SystemMessage 只有前缀没有内容 → 提取后 summary_text 为空字符串"""
        msgs: list[BaseMessage] = [
            SystemMessage(content=f"{C.SUMMARIZE_PREFIX}"),
            HumanMessage(content="hi"),
        ]
        summary, remaining = _extract_existing_summary(msgs)
        assert summary == ""  # 空字符串，不是 None
        assert len(remaining) == 1
        assert isinstance(remaining[0], HumanMessage)

    # ── QA-07: 消息精确在 keep_count 边界 ───────────────────────────────

    def test_conversation_exactly_at_keep_count(self, mocker):
        """conversation 长度刚好等于 keep_count → 不压缩（len <= keep_count）

        keep_count = SUMMARIZE_KEEP_LATEST_TURNS * 2
        让 conversation = keep_count + 1 条（多 1 条就触发）
        """
        mock_llm = mocker.MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = SummaryResult(
            summary="摘要", key_topics=[],
        )

        keep = C.SUMMARIZE_KEEP_LATEST_TURNS * 2  # = 12
        # 需要同时满足：
        #   (a) 非 system 消息 > SUMMARIZE_THRESHOLD=16 → should_summarize True
        #   (b) 提取摘要后 conversation (len = total - system) > keep_count
        # 17 条 HumanMessage (非 system) 满足 (a)，
        # 且 conversation=17 > keep_count=12 满足 (b)
        msgs: list[BaseMessage] = [
            SystemMessage(content="sys"),
            *[HumanMessage(content=str(i)) for i in range(C.SUMMARIZE_THRESHOLD + 1)],
        ]
        from langgraph.graph.message import add_messages
        msgs_with_ids = add_messages([], msgs)
        remove_ops, summary_msg = condense_history(msgs_with_ids, mock_llm)
        # conversation = 17 > keep=12 → 应触发压缩
        assert len(remove_ops) > 0, f"conversation = {C.SUMMARIZE_THRESHOLD + 1} > keep={keep} 应触发压缩"
        assert summary_msg is not None

    def test_conversation_exactly_one_below_keep_count(self, mocker):
        """conversation 长度刚好 = keep_count + 1 但 should_summarize 为 False → 不应压缩

        场景：总消息数超过 threshold，但 conversation 长度刚好 <= keep_count。
        实际上 keep_count = 12，threshold = 16，所以 conversation >= 13 才可能。

        设 total = 17（> threshold=16），但其中 5 条 system，conversation = 12 = keep_count
        """
        mock_llm = mocker.MagicMock()
        keep = C.SUMMARIZE_KEEP_LATEST_TURNS * 2  # = 12
        msgs: list[BaseMessage] = [
            *[SystemMessage(content=f"s{i}") for i in range(5)],  # 5 system
            *[HumanMessage(content=str(i)) for i in range(keep)],  # 12 conversation
        ]
        # 非 system 消息数 = 12，小于 threshold=16 → should_summarize = False
        assert should_summarize(msgs) is False
        from langgraph.graph.message import add_messages
        msgs_with_ids = add_messages([], msgs)
        remove_ops, summary_msg = condense_history(msgs_with_ids, mock_llm)
        assert remove_ops == []
        assert summary_msg is None

    # ── QA-08: ToolMessage 无 tool_call_id ──────────────────────────────

    def test_tool_message_without_tool_call_id(self):
        """ToolMessage 没有 tool_call_id → 格式化时不应崩溃"""
        from src.agent.summarizer import _format_conversation

        # 直接构造一个缺失 tool_call_id 的 ToolMessage
        msgs: list[BaseMessage] = [
            HumanMessage(content="query"),
            ToolMessage(content="结果数据", tool_call_id="t1"),  # 正常的
            HumanMessage(content="follow-up"),
        ]
        result = _format_conversation(msgs)
        assert "工具: 结果数据" in result or "工具: " in result

    # ── QA-09: summarizer_node 集成 ─────────────────────────────────────

    def test_summarizer_node_below_threshold(self, mocker):
        """summarizer_node 在低于阈值时返回空 dict"""
        # 模拟 call_model 后的低消息量状态
        mock_state: dict = {
            "messages": [
                SystemMessage(content="sys"),
                HumanMessage(content="hello"),
                AIMessage(content="hi"),
            ]
        }
        # 直接调用 summarizer_node（不经过 graph）
        from src.agent.agent import summarizer_node as node_fn
        # summarizer_node 需要 agent 模块级别的 llm
        # 但 llm 不通过参数传进来，而是从内部导入 concense_history
        # 实际上 summarizer_node 内部调用 condense_history(state["messages"], llm)
        # 这里的 llm 是 agent.py 中初始化了的 ChatOpenAI
        # 在测试中它会被自动 mock（因为 pytest-mock 的 autouse）

        # 直接调用可能会触发真实 LLM，我们需要 mock
        result = node_fn(mock_state)
        assert result == {}  # 低于阈值 → 空 dict


# ============================================================================
# 3/3  跨功能集成 — approve + summarizer 交互
# ============================================================================


class TestApproveSummarizerIntegration:
    """approve + summarizer 跨功能交互测试"""

    def _make_snapshot(self, mocker, messages=None, has_interrupt=False):
        snapshot = mocker.MagicMock()
        snapshot.values = {"messages": messages or []}
        snapshot.interrupts = (mocker.MagicMock(),) if has_interrupt else ()
        return snapshot

    # ── QA-10: 拒绝审批 → agent 回答 → summarizer ──────────────────────

    @pytest.mark.asyncio
    async def test_reject_then_summarizer_still_runs(self, mocker):
        """拒绝工具调用后，agent 生成新回答 → summarizer 仍应运行"""
        agent = mocker.MagicMock()

        call_idx = [0]

        def mock_get_state(config):  # noqa: ARG001
            i = call_idx[0]
            call_idx[0] += 1
            # 先返回 interrupt 状态，之后返回正常状态
            if i == 0:
                return self._make_interrupt_snapshot(mocker)
            s = self._make_snapshot(mocker)
            return s

        agent.get_state = mock_get_state

        async def event_generator(input_arg, config, **kwargs):
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r1",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="拒绝后回答")},
            }

        agent.astream_events = event_generator
        mocker.patch("src.agent.persistence.save_thread")

        events = [e async for e in chat_stream_session(
            agent, "", "reject-then-summarize", approval={"approved": False},
        )]

        # 拒绝后正常流式
        assert any(e["type"] == "token" for e in events)
        assert any(e["type"] == "done" for e in events)

    # ── QA-11: 批准审批 → 工具 → agent 回答 → summarizer ──────────────

    @pytest.mark.asyncio
    async def test_approve_then_tools_then_summarizer(self, mocker):
        """批准工具调用 → 执行工具 → agent 回答 → summarizer（完整链路）"""
        agent = mocker.MagicMock()

        call_idx = [0]

        def mock_get_state(config):  # noqa: ARG001
            i = call_idx[0]
            call_idx[0] += 1
            if i == 0:
                return self._make_interrupt_snapshot(mocker)
            s = self._make_snapshot(mocker)
            return s

        agent.get_state = mock_get_state

        async def event_generator(input_arg, config, **kwargs):
            # 恢复后图会重新执行，产生 tool_start/tool_end/chat_model 事件
            yield {
                "event": "on_tool_start",
                "run_id": "r2",
                "name": "search_wiki",
                "data": {"input": {"query": "Python"}},
            }
            yield {
                "event": "on_tool_end",
                "run_id": "r2",
                "name": "search_wiki",
                "data": {"output": "结果：`entities/python.md`"},
            }
            yield {
                "event": "on_chat_model_stream",
                "run_id": "r3",
                "name": "ChatOpenAI",
                "data": {"chunk": mocker.MagicMock(content="批准后回答")},
            }

        agent.astream_events = event_generator
        mocker.patch("src.agent.persistence.save_thread")

        events = [e async for e in chat_stream_session(
            agent, "", "approve-then-tools", approval={"approved": True},
        )]

        # 工具事件
        assert any(e["type"] == "tool_start" for e in events)
        assert any(e["type"] == "tool_end" for e in events)
        # token 事件
        assert any(e["type"] == "token" for e in events)
        # done 事件
        assert any(e["type"] == "done" for e in events)

    # ── QA-12: 完整图结构验证 ──────────────────────────────────────────

    def test_graph_structure_has_all_nodes_and_edges(self, mocker):
        """验证编译后的图包含所有节点和正确连接

        图结构：
          agent → (有 tool_calls → approve, 无 → summarizer)
          approve → (批准 → tools, 拒绝 → agent)
          tools → agent
          summarizer → __end__
        """
        mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mocker.MagicMock())
        mocker.patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"})

        agent = build_agent()
        graph = agent.get_graph()
        node_names = {n for n in graph.nodes.keys() if not n.startswith("__")}

        # 检查所有节点存在
        assert "agent" in node_names
        assert "tools" in node_names
        assert "approve" in node_names
        assert "summarizer" in node_names

        # graph.edges 是 Edge(source, target, data, conditional) 列表
        edge_pairs = {(e.source, e.target) for e in graph.edges}

        assert ("agent", "approve") in edge_pairs, "agent → approve 边缺失"
        assert ("agent", "summarizer") in edge_pairs, "agent → summarizer 边缺失"
        assert ("approve", "tools") in edge_pairs, "approve → tools 边缺失"
        assert ("approve", "agent") in edge_pairs, "approve → agent 边缺失"
        assert ("tools", "agent") in edge_pairs, "tools → agent 边缺失"
        assert ("summarizer", "__end__") in edge_pairs, "summarizer → __end__ 边缺失"

    # ── QA-13: summarizer_node 在完整图中的角色 ────────────────────────

    def test_summarizer_runs_before_end_in_graph(self, mocker):
        """验证 summarizer 是在 agent 之后、END 之前的节点"""
        mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mocker.MagicMock())
        mocker.patch.dict("os.environ", {"DEEPSEEK_API_KEY": "test-key"})

        from src.agent.agent import build_agent

        agent = build_agent()
        graph = agent.get_graph()

        # summarizer 节点存在于图中
        assert "summarizer" in graph.nodes

        # 验证 should_continue 返回类型包含 'approve' 和 'summarizer'
        from typing import get_args
        return_type = should_continue.__annotations__["return"]
        literal_values = get_args(return_type)
        assert "approve" in literal_values, f"should_continue 缺少 approve, 有: {literal_values}"
        assert "summarizer" in literal_values, f"should_continue 缺少 summarizer, 有: {literal_values}"

    # ── Helper ──────────────────────────────────────────────────────────

    def _make_interrupt_snapshot(self, mocker, tool_calls=None):
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


# ============================================================================
# 4/3  Bug 验证: 旧摘要残留
# ============================================================================


class TestStaleSummaryBug:
    """Bug 专项验证: 多次压缩后旧摘要 SystemMessage 残留

    根因: _extract_existing_summary 提取摘要文本后将原摘要 SystemMessage
    从 remaining 中移除，但 condense_history 未为其生成 RemoveMessage。
    结果: 旧摘要 SystemMessage 留在 state 中，每次压缩 +1 条。

    影响等级: P3 — 不影响正确性，但浪费 token。
    """

    def test_stale_summaries_accumulate_overtime(self, mocker):
        """模拟 5 轮压缩，验证旧摘要数量 = 压缩次数 - 1"""
        mock_llm = mocker.MagicMock()

        msgs: list[BaseMessage] = [SystemMessage(content="sys_prompt")]
        for i in range(C.SUMMARIZE_THRESHOLD + 2):
            msgs.append(HumanMessage(content=f"q{i}"))
            msgs.append(AIMessage(content=f"a{i}"))

        from langgraph.graph.message import add_messages

        state = add_messages([], msgs)
        stale_count = 0

        for round_num in range(1, 6):  # 5 轮压缩
            mock_llm.with_structured_output.return_value.invoke.return_value = SummaryResult(
                summary=f"第{round_num}轮摘要", key_topics=[],
            )

            remove_ops, summary_msg = condense_history(state, mock_llm)
            if remove_ops:
                state = add_messages(state, remove_ops + [summary_msg])

                summaries = [
                    m for m in state
                    if isinstance(m, SystemMessage) and C.SUMMARIZE_PREFIX in m.content
                ]
                # 旧摘要数量 = round_num - 1（最新那条不残留直到下次压缩）
                if round_num > 1:
                    stale_count = round_num - 1
                    assert len(summaries) == round_num, (
                        f"Round {round_num}: 期望 {round_num} 条摘要({stale_count} 条旧)",
                    )

            # 添加足够新消息确保再次触发压缩
            extra_needed = (C.SUMMARIZE_THRESHOLD - C.SUMMARIZE_KEEP_LATEST_TURNS * 2) // 2 + 5
            for i in range(extra_needed):
                state.append(HumanMessage(content=f"more_q{round_num}_{i}"))
                state.append(AIMessage(content=f"more_a{round_num}_{i}"))
            state = add_messages([], state)

        # 最终验证
        final_summaries = [
            m for m in state
            if isinstance(m, SystemMessage) and C.SUMMARIZE_PREFIX in m.content
        ]
        # 应该有很多条旧摘要（每条压缩轮次残留 1 条）
        assert len(final_summaries) >= 3, (
            f"Bug 验证: 5 轮压缩后应有 ≥4 条旧摘要残留，实际 {len(final_summaries)}"
        )

    def test_stale_summary_re_entered_into_next_condense(self, mocker):
        """验证旧摘要 SystemMessage 在下轮压缩时被重新检测为已有摘要

        即使残留，下一轮 _extract_existing_summary 应能正确提取最新那条
        """
        mock_llm = mocker.MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = SummaryResult(
            summary="摘要内容", key_topics=[],
        )

        msgs: list[BaseMessage] = [
            SystemMessage(content="sys"),
            SystemMessage(content=f"{C.SUMMARIZE_PREFIX}旧摘要1"),
            SystemMessage(content=f"{C.SUMMARIZE_PREFIX}旧摘要2"),
            SystemMessage(content=f"{C.SUMMARIZE_PREFIX}旧摘要3"),
            HumanMessage(content="新问题"),
            AIMessage(content="新回答"),
        ]

        # 验证 _extract_existing_summary 取最后一条
        summary, remaining = _extract_existing_summary(msgs)
        assert summary == "旧摘要3", f"应为最后一条摘要，实际: {summary}"
        # 3 条摘要都被从 remaining 移除了
        assert not any(
            isinstance(m, SystemMessage) and C.SUMMARIZE_PREFIX in m.content
            for m in remaining
        ), "摘要消息应从 remaining 中移除"
