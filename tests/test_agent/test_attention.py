"""
Attention Sink 锚定模块测试

覆盖范围:
  - detect_sinks: 显式模式匹配、强化检测
  - detect_frequent_entities: 频次统计自动锚定
  - merge_sinks: 合并、衰减、清理
  - format_sink_knowledge: 格式化输出
  - extract_sink_content: 纯文本提取
  - update_attention_sinks: 一站式更新
  - 边界条件：空输入、超长内容、置信度阈值
"""

import pytest

from src.agent.memory.attention import (
    detect_sinks,
    detect_frequent_entities,
    extract_sink_content,
    format_sink_knowledge,
    merge_sinks,
    update_attention_sinks,
)


# ============================================================================
# detect_sinks — 显式模式匹配
# ============================================================================


class TestDetectSinks:
    """detect_sinks 显式模式匹配"""

    def test_explicit_remember_pattern(self):
        """用户说"记住 X" → 应锚定"""
        new_sinks, reinforced = detect_sinks("记住我最喜欢的语言是 Python", None)
        assert len(new_sinks) == 1
        assert new_sinks[0]["type"] == "explicit"
        assert "最喜欢的语言是 Python" in new_sinks[0]["content"]
        assert new_sinks[0]["confidence"] == 0.8

    def test_name_introduction(self):
        """用户说"我叫 XXX" → 应锚定"""
        new_sinks, reinforced = detect_sinks("你好，我叫张三，是一名 Python 开发者", None)
        assert len(new_sinks) == 1
        assert "张三" in new_sinks[0]["content"]

    def test_important_marker(self):
        """用户说"重要的是 X" → 应锚定"""
        new_sinks, reinforced = detect_sinks("重要的是这个项目需要支持高并发", None)
        assert len(new_sinks) == 1
        assert "高并发" in new_sinks[0]["content"]

    def test_preference_pattern(self):
        """用户说"我喜欢 X" → 应锚定"""
        new_sinks, reinforced = detect_sinks("我喜欢用 VS Code 写代码", None)
        assert len(new_sinks) == 1
        assert "VS Code" in new_sinks[0]["content"]

    def test_no_pattern_no_sink(self):
        """无匹配模式 → 空列表"""
        new_sinks, reinforced = detect_sinks("今天天气怎么样？", None)
        assert len(new_sinks) == 0

    def test_empty_text(self):
        """空文本 → 空列表"""
        new_sinks, reinforced = detect_sinks("", None)
        assert len(new_sinks) == 0

    def test_reinforce_existing_sink(self):
        """已有锚定内容在文本中出现 → ID 出现在 reinforced 集合中"""
        existing = [{"id": "id1", "content": "Python 开发者", "type": "explicit"}]
        new_sinks, reinforced = detect_sinks("我作为 Python 开发者，想问个问题", existing)
        assert "id1" in reinforced

    def test_avoid_duplicate_content(self):
        """同一内容被重复检测 → 不生成重复锚定"""
        existing = [{"id": "id1", "content": "我喜欢编程", "type": "explicit"}]
        new_sinks, reinforced = detect_sinks("记住我喜欢编程", existing)
        assert len(new_sinks) == 0  # 已存在，不重复

    def test_multiple_patterns_in_one_message(self):
        """一条消息含多个模式 → 匹配第一个"""
        new_sinks, reinforced = detect_sinks("我叫张三。重要的是这个项目。", None)
        # 当前实现只选匹配到的第一个，因为 text 不会分多次匹配
        # 但至少应匹配到一个
        assert len(new_sinks) >= 1

    def test_context_after_colon(self):
        """'记住：X' 中文冒号后内容也能捕获"""
        new_sinks, reinforced = detect_sinks("记住：数据库要用 PostgreSQL", None)
        assert len(new_sinks) == 1
        assert "PostgreSQL" in new_sinks[0]["content"]

    def test_project_context(self):
        """'我的项目是 X' → 锚定"""
        new_sinks, reinforced = detect_sinks("我的项目是一个电商平台", None)
        assert len(new_sinks) == 1

    def test_very_long_content_truncated(self):
        """超长内容 → 截断到 SINK_CONTENT_MAX_CHARS"""
        long_text = "记住" + "x" * 500
        new_sinks, reinforced = detect_sinks(long_text, None)
        assert len(new_sinks) == 1
        assert len(new_sinks[0]["content"]) <= 200  # SINK_CONTENT_MAX_CHARS

    def test_note_pattern(self):
        """'请注意 X' → 锚定"""
        new_sinks, reinforced = detect_sinks("请注意这个接口有速率限制", None)
        assert len(new_sinks) == 1


# ============================================================================
# detect_frequent_entities — 频次统计
# ============================================================================


class TestDetectFrequentEntities:
    """detect_frequent_entities 频次锚定"""

    def test_entity_appears_3_times(self):
        """同一实体出现 3 次 → 自动锚定"""
        texts = ["Python 是一个好语言"] * 3
        new_sinks = detect_frequent_entities(texts, None)
        assert len(new_sinks) >= 1
        # 至少有一个是 Python
        python_sinks = [s for s in new_sinks if "Python" in s["content"]]
        assert len(python_sinks) >= 1

    def test_below_threshold_no_sink(self):
        """出现少于 3 次 → 不锚定"""
        texts = ["JavaScript 不错"] * 2
        new_sinks = detect_frequent_entities(texts, None)
        # 可能有其他匹配，但最少 JavaScript 不应该出现 3 次
        js_sinks = [s for s in new_sinks if "JavaScript" in s["content"]]
        assert len(js_sinks) == 0

    def test_existing_sink_skipped(self):
        """已锚定的内容 → 不重复添加"""
        texts = ["Python"] * 5
        existing = [{"id": "ex1", "content": "Python"}]
        new_sinks = detect_frequent_entities(texts, existing)
        python_sinks = [s for s in new_sinks if "Python" in s["content"]]
        assert len(python_sinks) == 0

    def test_empty_texts(self):
        """空列表 → 空结果"""
        assert detect_frequent_entities([], None) == []


# ============================================================================
# merge_sinks — 合并与衰减
# ============================================================================


class TestMergeSinks:
    """merge_sinks 合并、衰减、清理"""

    def test_new_sink_added(self):
        """新锚定 + 已有锚定 → 合并"""
        existing = [{
            "id": "id1", "content": "核心内容", "type": "explicit",
            "confidence": 0.8, "last_reinforced": 0, "idle_turns": 0,
        }]
        new_sinks = [{
            "id": "id2", "content": "新内容", "type": "explicit",
            "confidence": 0.8, "source_turn": 1, "last_reinforced": 1, "idle_turns": 0,
        }]
        merged = merge_sinks(existing, set(), new_sinks, [])
        assert len(merged) == 2

    def test_reinforced_sink_confidence_restored(self):
        """被强化的锚定 → 置信度恢复"""
        existing = [{
            "id": "id1", "content": "旧内容", "type": "explicit",
            "confidence": 0.3, "last_reinforced": 0, "idle_turns": 10,
        }]
        merged = merge_sinks(existing, {"id1"}, [], [])
        assert len(merged) == 1
        assert merged[0]["confidence"] >= 0.9  # 重置为 SINK_CONFIDENCE_REINFORCE
        assert merged[0]["idle_turns"] == 0  # 重置闲置计数

    def test_unreinforced_sink_decays(self):
        """未被强化 → 超过 SINK_REINFORCE_TURNS 后衰减"""
        existing = [{
            "id": "id1", "content": "旧内容", "type": "explicit",
            "confidence": 0.5, "last_reinforced": 0, "idle_turns": 5,
        }]
        merged = merge_sinks(existing, set(), [], [])
        assert merged[0]["confidence"] < 0.5  # 已衰减

    def test_low_confidence_sink_removed(self):
        """置信度低于阈值 → 移除"""
        existing = [{
            "id": "id1", "content": "过期内容", "type": "explicit",
            "confidence": 0.1, "last_reinforced": 0, "idle_turns": 20,
        }]
        merged = merge_sinks(existing, set(), [], [])
        assert len(merged) == 0

    def test_sorted_by_confidence(self):
        """合并后按置信度降序"""
        existing = [
            {"id": "id1", "content": "a", "type": "explicit",
             "confidence": 0.5, "last_reinforced": 0, "idle_turns": 0},
            {"id": "id2", "content": "b", "type": "explicit",
             "confidence": 0.9, "last_reinforced": 0, "idle_turns": 0},
        ]
        merged = merge_sinks(existing, set(), [], [])
        assert merged[0]["id"] == "id2"
        assert merged[1]["id"] == "id1"

    def test_empty_existing(self):
        """空已存在 + 有新锚定 → 返回新锚定"""
        merged = merge_sinks([], set(), [], [])
        assert merged == []

    def test_capacity_limit(self):
        """超过 ATTENTION_SINK_MAX 时限制数量"""
        many_sinks = [
            {"id": f"id{i}", "content": f"内容{i}", "type": "explicit",
             "confidence": 0.8, "last_reinforced": 0, "idle_turns": 0}
            for i in range(20)
        ]
        from src.agent import constants as C
        merged = merge_sinks(many_sinks, set(), [], [])
        assert len(merged) <= C.ATTENTION_SINK_MAX


# ============================================================================
# format_sink_knowledge — 格式化
# ============================================================================


class TestFormatSinkKnowledge:
    """format_sink_knowledge 格式化输出"""

    def test_formats_with_confidence(self):
        """格式化包含置信度"""
        sinks = [{
            "id": "id1", "content": "我喜欢 Python", "type": "explicit",
            "confidence": 0.8,
        }]
        result = format_sink_knowledge(sinks)
        assert "Python" in result
        assert "80%" in result or "0.8" in result

    def test_empty_list(self):
        """空列表 → 空字符串"""
        assert format_sink_knowledge([]) == ""

    def test_type_icons(self):
        """不同类型有不同 icon"""
        explicit_sink = [{
            "id": "id1", "content": "显式内容", "type": "explicit", "confidence": 0.8,
        }]
        freq_sink = [{
            "id": "id2", "content": "频繁内容", "type": "frequency", "confidence": 0.6,
        }]
        explicit_result = format_sink_knowledge(explicit_sink)
        freq_result = format_sink_knowledge(freq_sink)
        # 显式用 📌
        assert "📌" in explicit_result
        # 频次用 🔄
        assert "🔄" in freq_result


# ============================================================================
# extract_sink_content — 纯文本提取
# ============================================================================


class TestExtractSinkContent:
    """extract_sink_content 纯文本提取"""

    def test_extracts_content(self):
        sinks = [{
            "id": "id1", "content": "Python 专家", "type": "explicit", "confidence": 0.8,
        }]
        assert extract_sink_content(sinks) == "Python 专家"

    def test_multiple_sinks(self):
        sinks = [
            {"id": "id1", "content": "Python", "type": "explicit", "confidence": 0.8},
            {"id": "id2", "content": "FastAPI", "type": "frequency", "confidence": 0.6},
        ]
        assert "Python" in extract_sink_content(sinks)
        assert "FastAPI" in extract_sink_content(sinks)

    def test_empty_list(self):
        assert extract_sink_content([]) == ""

    def test_empty_content_skipped(self):
        sinks = [{"id": "id1", "content": "", "type": "explicit", "confidence": 0.8}]
        assert extract_sink_content(sinks) == ""


# ============================================================================
# update_attention_sinks — 一站式整合
# ============================================================================


class TestUpdateAttentionSinks:
    """update_attention_sinks 一站式接口"""

    def test_basic_detection_and_merge(self):
        """从用户输入检测并合并"""
        result = update_attention_sinks("记住我喜欢 Python", [], ["Python"])
        assert len(result) >= 1
        assert any("Python" in s["content"] for s in result)

    def test_no_history_no_crash(self):
        """无历史文本 → 正常运作"""
        result = update_attention_sinks("你好", [])
        assert isinstance(result, list)

    def test_reinforce_existing(self):
        """提现已有锚定内容 → 强化"""
        existing = [{
            "id": "id1", "content": "Python", "type": "explicit",
            "confidence": 0.4, "last_reinforced": 0, "idle_turns": 8,
        }]
        result = update_attention_sinks("关于 Python 的问题", existing)
        # 内容 Python 被强化 → 置信度恢复
        for s in result:
            if s["content"] == "Python":
                assert s["confidence"] >= 0.9
                break
        else:
            pytest.fail("Python sink not found in result")
