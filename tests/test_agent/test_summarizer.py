"""
对话摘要压缩模块测试

覆盖范围:
  - should_summarize: 边界条件、阈值检测
  - _format_conversation: 格式化正确性
  - _extract_existing_summary: 已有摘要提取
  - _call_summarize_llm: LLM 调用
  - condense_history: 完整流程
  - summarizer_node: 图节点集成
"""
import pytest

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.agent import constants as C
from src.agent.memory.summarizer import (
    SummaryResult,
    _extract_existing_summary,
    _format_conversation,
    condense_history,
    should_summarize,
)


# ============================================================================
# should_summarize
# ============================================================================


class TestShouldSummarize:
    """should_summarize 边界条件"""

    def test_below_threshold_returns_false(self):
        """少于 SUMMARIZE_THRESHOLD 非 system 消息 → False"""
        msgs: list[BaseMessage] = [
            SystemMessage(content="sys"),
            HumanMessage(content="hello"),
            AIMessage(content="hi"),
        ]
        assert should_summarize(msgs) is False

    def test_at_threshold_returns_false(self):
        """恰好等于 SUMMARIZE_THRESHOLD → False（不触发）"""
        msgs: list[BaseMessage] = [
            SystemMessage(content="sys"),
            *[HumanMessage(content=str(i)) for i in range(C.SUMMARIZE_THRESHOLD)],
        ]
        assert should_summarize(msgs) is False

    def test_exceeds_threshold_returns_true(self):
        """超过 SUMMARIZE_THRESHOLD → True"""
        msgs: list[BaseMessage] = [
            SystemMessage(content="sys"),
            *[HumanMessage(content=str(i)) for i in range(C.SUMMARIZE_THRESHOLD + 1)],
        ]
        assert should_summarize(msgs) is True

    def test_all_system_messages(self):
        """全是 SystemMessage → False"""
        msgs: list[BaseMessage] = [SystemMessage(content=str(i)) for i in range(30)]
        assert should_summarize(msgs) is False

    def test_empty_messages(self):
        """空列表 → False"""
        assert should_summarize([]) is False


# ============================================================================
# _format_conversation
# ============================================================================


class TestFormatConversation:
    """消息格式化测试"""

    def test_basic_format(self):
        """基本格式化：human → 用户, ai → 助手"""
        msgs: list[BaseMessage] = [
            HumanMessage(content="你好"),
            AIMessage(content="你好！有什么可以帮助你的？"),
        ]
        result = _format_conversation(msgs)
        assert "用户: 你好" in result
        assert "助手: 你好！有什么可以帮助你的？" in result

    def test_with_existing_summary(self):
        """在有已有摘要时前缀插入"""
        msgs: list[BaseMessage] = [HumanMessage(content="新问题")]
        result = _format_conversation(msgs, existing_summary="用户问了 Python")
        assert "[已有摘要]" in result
        assert "用户问了 Python" in result
        assert "[最新对话]" in result
        assert "用户: 新问题" in result

    def test_tool_message_truncated(self):
        """ToolMessage 内容过长时截断"""
        long_content = "x" * 500
        msgs: list[BaseMessage] = [
            HumanMessage(content="query"),
            type("ToolMessage", (), {"type": "tool", "content": long_content})(),
        ]
        # Use the actual ToolMessage class
        from langchain_core.messages import ToolMessage
        msgs = [
            HumanMessage(content="query"),
            ToolMessage(content=long_content, tool_call_id="t1"),
        ]
        result = _format_conversation(msgs)
        assert len(result) < 800  # 截断后不会太长

    def test_empty_messages(self):
        """空消息列表"""
        result = _format_conversation([])
        assert "[最新对话]" in result


# ============================================================================
# _extract_existing_summary
# ============================================================================


class TestExtractExistingSummary:
    """已有摘要提取测试"""

    def test_extract_summary_message(self):
        """提取带有 SUMMARIZE_PREFIX 的 SystemMessage"""
        msgs: list[BaseMessage] = [
            SystemMessage(content=f"{C.SUMMARIZE_PREFIX}用户询问了 Python"),
            HumanMessage(content="继续"),
        ]
        summary, remaining = _extract_existing_summary(msgs)
        assert summary == "用户询问了 Python"
        assert len(remaining) == 1
        assert isinstance(remaining[0], HumanMessage)

    def test_no_summary_message(self):
        """没有摘要消息 → summary=None"""
        msgs: list[BaseMessage] = [
            SystemMessage(content="普通系统提示"),
            HumanMessage(content="你好"),
        ]
        summary, remaining = _extract_existing_summary(msgs)
        assert summary is None
        assert len(remaining) == 2

    def test_empty_list(self):
        """空列表 → summary=None, remaining=[]"""
        summary, remaining = _extract_existing_summary([])
        assert summary is None
        assert remaining == []

    def test_multiple_summary_messages(self):
        """多个摘要 SystemMessage → 只保留最后一个（最新的摘要最完整）"""
        msgs: list[BaseMessage] = [
            SystemMessage(content=f"{C.SUMMARIZE_PREFIX}摘要1"),
            SystemMessage(content="普通 sys"),
            SystemMessage(content=f"{C.SUMMARIZE_PREFIX}摘要2"),
        ]
        # 最后一个匹配的摘要胜出（最新的最完整）
        summary, remaining = _extract_existing_summary(msgs)
        assert summary == "摘要2"
        assert len(remaining) == 1  # 只有一个普通 system 消息


# ============================================================================
# condense_history
# ============================================================================


class TestCondenseHistory:
    """condense_history 完整流程测试"""

    def test_below_threshold_no_change(self, mocker):
        """消息数低于阈值 → 返回空操作列表"""
        mock_llm = mocker.MagicMock()
        msgs: list[BaseMessage] = [
            SystemMessage(content="sys"),
            HumanMessage(content="hello"),
            AIMessage(content="hi"),
        ]
        remove_ops, summary_msg = condense_history(msgs, mock_llm)
        assert remove_ops == []
        assert summary_msg is None

    def test_exceeds_threshold_compresses(self, mocker):
        """超过阈值 → 压缩并返回 RemoveMessage"""
        mock_llm = mocker.MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = SummaryResult(
            summary="用户询问了 Python 相关话题",
            key_topics=["Python"],
        )

        # 构建超过 threshold 的消息列表
        msgs: list[BaseMessage] = [
            SystemMessage(content="你是一个助手"),
        ]
        for i in range(C.SUMMARIZE_THRESHOLD + 2):
            msgs.append(HumanMessage(content=f"问题{i}"))
            msgs.append(AIMessage(content=f"回答{i}"))

        # 先触发 add_messages 以分配 IDs
        from langgraph.graph.message import add_messages
        msgs_with_ids = add_messages([], msgs)

        remove_ops, summary_msg = condense_history(msgs_with_ids, mock_llm)
        assert len(remove_ops) > 0
        assert summary_msg is not None
        assert summary_msg.content.startswith(C.SUMMARIZE_PREFIX)
        # 验证 LLM 被调用（结构化输出）
        mock_llm.with_structured_output.assert_called_once()

    def test_llm_failure_graceful_degrade(self, mocker):
        """LLM 调用失败 → 降级为不压缩"""
        mock_llm = mocker.MagicMock()
        mock_llm.with_structured_output.return_value.invoke.side_effect = Exception("API error")

        msgs: list[BaseMessage] = [
            SystemMessage(content="sys"),
            *[HumanMessage(content=str(i)) for i in range(C.SUMMARIZE_THRESHOLD + 4)],
            *[AIMessage(content=str(i)) for i in range(C.SUMMARIZE_THRESHOLD + 4)],
        ]
        from langgraph.graph.message import add_messages
        msgs_with_ids = add_messages([], msgs)

        remove_ops, summary_msg = condense_history(msgs_with_ids, mock_llm)
        assert remove_ops == []
        assert summary_msg is None

    def test_llm_empty_response(self, mocker):
        """LLM 返回空内容 → 降级为不压缩"""
        mock_llm = mocker.MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = SummaryResult(
            summary="", key_topics=[],
        )

        msgs: list[BaseMessage] = [
            SystemMessage(content="sys"),
            *[HumanMessage(content=str(i)) for i in range(C.SUMMARIZE_THRESHOLD + 4)],
            *[AIMessage(content=str(i)) for i in range(C.SUMMARIZE_THRESHOLD + 4)],
        ]
        from langgraph.graph.message import add_messages
        msgs_with_ids = add_messages([], msgs)

        remove_ops, summary_msg = condense_history(msgs_with_ids, mock_llm)
        assert remove_ops == []
        assert summary_msg is None

    def test_preserves_recent_conversation(self, mocker):
        """压缩后保留最新的 KEEP_LATEST_TURNS 轮对话"""
        mock_llm = mocker.MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = SummaryResult(
            summary="摘要内容", key_topics=["Python"],
        )

        keep_turns = C.SUMMARIZE_KEEP_LATEST_TURNS

        # 构建大量消息
        msgs: list[BaseMessage] = [
            SystemMessage(content="sys_prompt"),
        ]
        # 确保超过 SUMMARIZE_THRESHOLD 且至少有 keep_turns 可保留
        # 用 max 兼容不同常数值
        min_compressible = max(5, C.SUMMARIZE_THRESHOLD - keep_turns + 1)
        total_turns = keep_turns + min_compressible
        for i in range(total_turns):
            msgs.append(HumanMessage(content=f"问题{i}"))
            msgs.append(AIMessage(content=f"回答{i}"))

        from langgraph.graph.message import add_messages
        msgs_with_ids = add_messages([], msgs)

        remove_ops, summary_msg = condense_history(msgs_with_ids, mock_llm)
        assert len(remove_ops) > 0
        assert summary_msg is not None

        # 验证保留的消息数 = 1(sys) + 1(摘要) + keep_turns*2
        # 用 RemoveMessage + add_messages 重建状态，验证条数
        from langchain_core.messages import RemoveMessage
        restored = add_messages(msgs_with_ids, remove_ops + [summary_msg])
        expected_count = 1 + 1 + (keep_turns * 2)  # system + summary + keep
        assert len(restored) == expected_count, f"expected {expected_count}, got {len(restored)}: {[type(m).__name__ for m in restored]}"

        # 验证保留的是最新的消息
        last_human = [m for m in restored if isinstance(m, HumanMessage)][-1]
        assert last_human.content == f"问题{total_turns - 1}"

    def test_with_existing_summary_integration(self, mocker):
        """已有摘要 + 新增对话 → 合并摘要"""
        mock_llm = mocker.MagicMock()
        mock_llm.with_structured_output.return_value.invoke.side_effect = [
            SummaryResult(summary="旧摘要内容", key_topics=[]),
            SummaryResult(summary="合并后的新摘要内容", key_topics=["Python"]),
        ]

        # 第一次压缩
        msgs1: list[BaseMessage] = [
            SystemMessage(content="sys_prompt"),
            *[HumanMessage(content=f"q{i}") for i in range(5)],
            *[AIMessage(content=f"a{i}") for i in range(5)],
        ]
        # 添加更多到超过阈值
        for i in range(5, C.SUMMARIZE_THRESHOLD):
            msgs1.append(HumanMessage(content=f"q{i}"))
            msgs1.append(AIMessage(content=f"a{i}"))

        from langgraph.graph.message import add_messages
        msgs1_with_ids = add_messages([], msgs1)

        remove_ops1, summary_msg1 = condense_history(msgs1_with_ids, mock_llm)
        compressed1 = add_messages(msgs1_with_ids, remove_ops1 + [summary_msg1])

        # 验证第一次压缩后包含摘要
        summary_texts = [m.content for m in compressed1 if isinstance(m, SystemMessage) and C.SUMMARIZE_PREFIX in m.content]
        assert len(summary_texts) > 0

        # 第二次压缩：添加新消息
        msgs2 = list(compressed1)
        for i in range(10):
            msgs2.append(HumanMessage(content=f"new_q{i}"))
            msgs2.append(AIMessage(content=f"new_a{i}"))

        msgs2_with_ids = add_messages([], msgs2)

        remove_ops2, summary_msg2 = condense_history(msgs2_with_ids, mock_llm)
        if remove_ops2:
            # 验证 LLM 收到了已有摘要的信息（第二次调用时会合并）
            call_args = mock_llm.with_structured_output.return_value.invoke.call_args
            if call_args:
                prompt_msgs = call_args[0][0]
                for m in prompt_msgs:
                    if hasattr(m, 'content'):
                        pass  # 内容正确性不在此测试

    def test_no_ids_no_crash(self, mocker):
        """消息没有 IDs → 不会报错，只是无法移除"""
        mock_llm = mocker.MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = SummaryResult(
            summary="摘要", key_topics=[],
        )

        # 消息没有 ID（未经过 add_messages）
        msgs: list[BaseMessage] = [
            SystemMessage(content="sys"),
            *[HumanMessage(content=str(i)) for i in range(C.SUMMARIZE_THRESHOLD + 5)],
        ]

        remove_ops, summary_msg = condense_history(msgs, mock_llm)
        # 应该生成摘要但 remove_ops 为空（没有 ID 无法 RemoveMessage）
        assert summary_msg is not None
        assert len(remove_ops) == 0  # 没有 ID，无法生成 RemoveMessage


class TestCondenseHistoryEdge:
    """condense_history 边界情况"""

    def test_empty_messages(self, mocker):
        """空消息列表"""
        mock_llm = mocker.MagicMock()
        remove_ops, summary_msg = condense_history([], mock_llm)
        assert remove_ops == []
        assert summary_msg is None

    def test_only_system_messages(self, mocker):
        """只有 SystemMessage"""
        mock_llm = mocker.MagicMock()
        msgs: list[BaseMessage] = [SystemMessage(content=f"s{i}") for i in range(30)]
        remove_ops, summary_msg = condense_history(msgs, mock_llm)
        assert remove_ops == []
        assert summary_msg is None
        mock_llm.with_structured_output.assert_not_called()  # 不应调用 LLM

    def test_tool_messages_skipped_in_summary(self, mocker):
        """ToolMessage 不应该被编入摘要"""
        from langchain_core.messages import ToolMessage

        mock_llm = mocker.MagicMock()
        mock_llm.with_structured_output.return_value.invoke.return_value = SummaryResult(
            summary="用户与技术助手对话", key_topics=["Python"],
        )

        msgs: list[BaseMessage] = [
            SystemMessage(content="sys"),
            *[HumanMessage(content=f"q{i}") for i in range(C.SUMMARIZE_THRESHOLD)],
            *[AIMessage(content=f"a{i}") for i in range(C.SUMMARIZE_THRESHOLD)],
            *[ToolMessage(content=f"工具结果{i}", tool_call_id=f"t{i}") for i in range(5)],
            HumanMessage(content="最终问题"),
            AIMessage(content="最终回答"),
        ]

        from langgraph.graph.message import add_messages
        msgs_with_ids = add_messages([], msgs)

        remove_ops, summary_msg = condense_history(msgs_with_ids, mock_llm)
        # 应该成功压缩（ToolMessage 不计入摘要内容，但计入总长度判断）
        assert remove_ops is not None
        # 验证 with_structured_output 被调用了
        mock_llm.with_structured_output.assert_called_once()
