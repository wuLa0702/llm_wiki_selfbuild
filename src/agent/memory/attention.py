"""
Attention Sink 模块 — 对话关键信息锚定

职责：
  - 从用户消息中检测"需记住"的关键信息（显式指令 + 频次统计）
  - 维护锚定信息的置信度和衰减
  - 格式化锚定信息供 LLM 上下文注入
  - 跨摘要压缩保持锚定信息不丢失

设计原理：
  Attention Sink 是"工作记忆"的补充机制。
  工作记忆（messages[]）是线性的、会压缩的；
  而 Attention Sink 是结构化的、持久化的、跨压缩存活的。

生命周期：
  检测（用户每轮输入）→ 置信度评估 → 合并/衰减 → 注入 LLM → 持久化
"""

import logging
import re
from typing import Any

from src.agent import constants as C

logger = logging.getLogger("agent.attention")


# ── 模式匹配集合 ──────────────────────────────────────────────────────────────

# 从常量编译模式（模块加载时一次编译）
_SINK_REGEXES = [re.compile(re.escape(p) + r"[:：\s]*(.+)") for p in C.SINK_PATTERNS]
# 简短模式不需要冒号分割
_SINK_SHORT_PATTERNS = {p for p in C.SINK_PATTERNS if len(p) <= 3}


# ── 工具函数 ──────────────────────────────────────────────────────────────────


def _generate_sink_id(content: str, sink_type: str) -> str:
    """生成锚定唯一 ID

    基于内容 + 类型的简单哈希，相同内容复用 ID。
    """
    raw = f"{sink_type}:{content}"
    return str(hash(raw)) if raw else ""


def _now() -> int:
    """获取当前轮次（简化实现：用模块级计数器）"""
    if not hasattr(_now, "counter"):
        _now.counter = 0
    _now.counter += 1
    return _now.counter


# ── 检测 ──────────────────────────────────────────────────────────────────────


def detect_sinks(text: str, existing_sinks: list[dict] | None = None) -> list[dict]:
    """从用户输入文本中检测 Attention Sink

    检测策略（可组合）：
      1. 显式模式匹配：用户说"记住 X"、"我叫 X"等
      2. 频次统计：同一实体反复出现时自动锚定
      3. 强化：已有锚定被再次提及时提升置信度

    Args:
        text: 用户输入的文本
        existing_sinks: 已有的锚定列表，用于去重和强化

    Returns:
        新检测到的 sink dict 列表
    """
    new_sinks: list[dict] = []
    seen_content = {s.get("content", "") for s in (existing_sinks or [])}
    turn = _now()

    # ── 策略 1: 显式模式匹配 ───────────────────────────────────
    # 按列表顺序取第一个匹配（优先级由 SINK_PATTERNS 顺序决定）
    for pattern, regex in zip(C.SINK_PATTERNS, _SINK_REGEXES):
        match = regex.search(text)
        if match:
            content = match.group(1).strip()
            if len(content) >= C.SINK_PATTERN_MIN_LENGTH and content not in seen_content:
                content = content[:C.SINK_CONTENT_MAX_CHARS]
                new_sinks.append({
                    "id": _generate_sink_id(content, "explicit"),
                    "type": "explicit",
                    "content": content,
                    "confidence": C.SINK_CONFIDENCE_NEW,
                    "source_turn": turn,
                    "last_reinforced": turn,
                    "idle_turns": 0,
                })
                seen_content.add(content)
                logger.info("Attention Sink 显式锚定 | content=%s", content[:40])
            # 找到第一个匹配即停止（避免子串模式冲突）
            break

    # ── 策略 2: 强化已有锚定 ──────────────────────────────────
    reinforced_ids: set[str] = set()
    for sink in (existing_sinks or []):
        content = sink.get("content", "")
        if content and content in text:
            reinforced_ids.add(sink.get("id", ""))
            logger.debug("Attention Sink 强化 | id=%s content=%s", sink["id"], content[:30])

    return new_sinks, reinforced_ids


def detect_frequent_entities(
    messages_texts: list[str],
    existing_sinks: list[dict] | None = None,
) -> list[dict]:
    """频次统计：扫描所有对话中出现≥N 次的名词/术语

    用于自动锚定反复出现但用户没有显式要求记住的信息。
    如：项目中反复提及的技术术语、产品名等。

    Args:
        messages_texts: 对话消息的文本列表
        existing_sinks: 已有的锚定

    Returns:
        频次触发的 sink dict 列表
    """
    existing_content = {s.get("content", "") for s in (existing_sinks or [])}
    turn = _now()
    # 简单分词统计：取中文 2-4 字片段 + 英文单词
    words: dict[str, int] = {}

    for text in messages_texts:
        # 英文单词（≥3 字符）— 计数用 lowercased，存储用原名
        for w in re.findall(r'[A-Za-z]\w{2,}', text):
            words[w] = words.get(w, 0) + 1
        # 中文词组（2-4 字）
        for c in re.findall(r'[一-鿿]{2,4}', text):
            words[c] = words.get(c, 0) + 1

    new_sinks: list[dict] = []
    for word, count in words.items():
        if count >= C.FREQUENCY_SINK_THRESHOLD and word not in existing_content:
            new_sinks.append({
                "id": _generate_sink_id(word, "frequency"),
                "type": "frequency",
                "content": word,
                "confidence": min(0.5 + count * 0.1, 0.9),
                "source_turn": turn,
                "last_reinforced": turn,
                "idle_turns": 0,
            })
            logger.info("Attention Sink 频次锚定 | content=%s count=%d", word, count)

    return new_sinks


# ── 合并与衰减 ────────────────────────────────────────────────────────────────


def merge_sinks(
    existing_sinks: list[dict],
    reinforced_ids: set[str],
    new_sinks: list[dict],
    frequency_sinks: list[dict],
) -> list[dict]:
    """合并新旧锚定，应用衰减

    ═══════════════════════════════════════════════════════════════
    容量、长度与置信度规则（定义见 constants.py）
    ═══════════════════════════════════════════════════════════════

    输入长度保护：
      - 单条 content 上限 SINK_CONTENT_MAX_CHARS = 200
        （超长截断，防御性安全网，上游也截断）
      - 新锚定（new_sinks + frequency_sinks）批量上限 SINK_NEW_BATCH_MAX = 10
        （防止单次合并处理过多新增条目）

    输出长度保护：
      - 条目数上限：ATTENTION_SINK_MAX = 15
      - 所有 content 总字符上限：SINK_OUTPUT_MAX_CHARS = 3000
        （超出时丢弃最低置信度锚定，直至总字符达标）

    置信度衰减规则：
      - 新锚定初始 confidence = SINK_CONFIDENCE_NEW = 0.8
      - 被强化（用户再次提及）→ 重置为 SINK_CONFIDENCE_REINFORCE = 0.9
      - 未强化 → idle_turns += 1
      - idle_turns >= SINK_REINFORCE_TURNS = 5 后开始衰减
      - 每轮衰减 SINK_DECAY_PER_TURN = 0.05（朝 0 递减，不下负）

    移除条件（任一满足即移除）：
      ① confidence < ATTENTION_SINK_MIN_CONFIDENCE = 0.3
      ② idle_turns > SINK_MAX_IDLE_TURNS = 20

    排序：返回列表按 confidence 降序排列，高置信度锚定优先。

    ═══════════════════════════════════════════════════════════════

    Args:
        existing_sinks: 已有的锚定列表
        reinforced_ids: 本轮被强化的锚定 ID 集合
        new_sinks: 模型匹配新增的锚定
        frequency_sinks: 频次触发的锚定

    Returns:
        合并后的锚定列表（ATTENTION_SINK_MAX 上限 + SINK_OUTPUT_MAX_CHARS 上限，已排序）
    """
    turn = _now()
    merged: list[dict] = []
    seen_ids: set[str] = set()

    # 0a. 防御性：截断每项 content 超长文本
    def _truncate_content(sink: dict) -> dict:
        content = sink.get("content", "")
        if isinstance(content, str) and len(content) > C.SINK_CONTENT_MAX_CHARS:
            sink["content"] = content[:C.SINK_CONTENT_MAX_CHARS]
        return sink

    # 0b. 防御性：截断新增锚定批量上限，防止调用方传超大列表
    input_new_sinks = (new_sinks or [])[:C.SINK_NEW_BATCH_MAX]
    input_freq_sinks = (frequency_sinks or [])[:C.SINK_NEW_BATCH_MAX]

    # 1. 处理已有锚定（受容量限制）
    for sink in existing_sinks:
        if len(merged) >= C.ATTENTION_SINK_MAX:
            logger.debug("Attention Sink 容量已达上限 | count=%d", len(merged))
            break
        _truncate_content(sink)
        sid = sink.get("id", "")
        if sid in reinforced_ids:
            # 被强化 → 恢复置信度
            sink["confidence"] = C.SINK_CONFIDENCE_REINFORCE
            sink["last_reinforced"] = turn
            sink["idle_turns"] = 0
        else:
            # 未被强化 → 衰减
            sink["idle_turns"] = sink.get("idle_turns", 0) + 1
            if sink["idle_turns"] >= C.SINK_REINFORCE_TURNS:
                sink["confidence"] = max(0, sink.get("confidence", 0) - C.SINK_DECAY_PER_TURN)

        # 清理条件
        if sink["confidence"] < C.ATTENTION_SINK_MIN_CONFIDENCE:
            logger.info("Attention Sink 过期移除 | content=%s confidence=%.2f",
                        sink.get("content", "")[:30], sink["confidence"])
            continue
        if sink["idle_turns"] > C.SINK_MAX_IDLE_TURNS:
            logger.info("Attention Sink 超时移除 | content=%s idle=%d",
                        sink.get("content", "")[:30], sink["idle_turns"])
            continue

        merged.append(sink)
        seen_ids.add(sid)

    # 2. 追加新锚定（容量上限 + 输入批量上限已截断）
    for sink in input_new_sinks + input_freq_sinks:
        _truncate_content(sink)
        sid = sink.get("id", "")
        if sid not in seen_ids and len(merged) < C.ATTENTION_SINK_MAX:
            merged.append(sink)
            seen_ids.add(sid)

    # 3. 按置信度降序排序
    merged.sort(key=lambda s: s.get("confidence", 0), reverse=True)

    # 4. 输出总长度保护：如果所有 content 总字符超出上限，从尾部（低置信度）开始丢弃
    total_chars = sum(len(s.get("content", "")) for s in merged)
    if total_chars > C.SINK_OUTPUT_MAX_CHARS:
        logger.info("Attention Sink 输出超长 | 总字符=%d 上限=%d 丢弃低置信度锚定",
                     total_chars, C.SINK_OUTPUT_MAX_CHARS)
        # 已按 confidence 降序排列，从尾部逆向丢弃
        while merged and sum(len(s.get("content", "")) for s in merged) > C.SINK_OUTPUT_MAX_CHARS:
            dropped = merged.pop()
            logger.debug("Attention Sink 因输出长度限制丢弃 | content=%s confidence=%.2f",
                         dropped.get("content", "")[:30], dropped.get("confidence", 0))

    return merged


# ── 格式化 ────────────────────────────────────────────────────────────────────


def format_sink_knowledge(sinks: list[dict]) -> str:
    """将锚定信息格式化为 SystemMessage content

    返回的文本注入到 LLM 上下文中，让模型感知用户的重要信息。

    Args:
        sinks: 锚定列表（按置信度排序）

    Returns:
        格式化后的信息文本
    """
    if not sinks:
        return ""

    lines: list[str] = []
    for i, sink in enumerate(sinks, 1):
        content = sink.get("content", "")
        sink_type = sink.get("type", "unknown")
        confidence = sink.get("confidence", 0)

        type_label = {"explicit": "📌", "frequency": "🔄"}.get(sink_type, "•")
        lines.append(f"{i}. {type_label} {content} (置信度: {confidence:.0%})")

    return C.SINK_SYSTEM_PROMPT.format(sink_lines="\n".join(lines))


def extract_sink_content(sinks: list[dict]) -> str:
    """仅提取锚定内容的纯文本（用于摘要的上下文保留）

    不带格式和置信度，只取核心知识。

    Args:
        sinks: 锚定列表

    Returns:
        逗号分隔的锚定内容
    """
    contents = [s.get("content", "") for s in sinks if s.get("content")]
    return "、".join(contents) if contents else ""


# ── 整合接口 ──────────────────────────────────────────────────────────────────


def update_attention_sinks(
    user_text: str,
    existing_sinks: list[dict],
    history_texts: list[str] | None = None,
) -> list[dict]:
    """一站式更新 Attention Sink

    Args:
        user_text: 用户本轮输入
        existing_sinks: 现有的锚定列表
        history_texts: 可选的对话历史文本（用于频次统计）

    Returns:
        更新后的锚定列表
    """
    # 1. 检测显式模式 + 已存在的强化
    new_sinks, reinforced_ids = detect_sinks(user_text, existing_sinks)

    # 2. 每 N 轮检查一次频次锚定（频率锚定用历史文本）
    frequency_sinks: list[dict] = []
    if history_texts and (_now.counter % 3 == 0):  # 每 3 轮扫一次频次
        frequency_sinks = detect_frequent_entities(history_texts, existing_sinks)

    # 3. 合并、衰减、清理
    return merge_sinks(existing_sinks or [], reinforced_ids, new_sinks, frequency_sinks)
