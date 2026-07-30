"""
感知模块 — 用户意图分类

将用户输入分类为不同的意图类型，影响后续图路由决策。

设计：
  - 规则优先：基于关键词快速分类，无需 LLM 调用
  - LLM 兜底：规则不匹配时使用结构化 LLM 调用
  - 默认 search：无法确定时降级为 search（不阻断用户查询）

接口：
  classify_intent(text: str) -> dict     — 纯规则分类（向后兼容）
  classify_user_intent(text, llm)        — 规则 + LLM 兜底
  intent_classifier_node(state)          — LangGraph 图节点函数
"""

import logging
import re
from typing import Any

from src.agent import constants as C

logger = logging.getLogger("agent.intent")


# ── 匹配规则 ──────────────────────────────────────────────────────────────────


def _has_chinese(text: str) -> bool:
    """检测文本是否含中文字符"""
    return bool(re.search(r'[一-鿿]', text))


def _match_greeting(text: str) -> bool:
    """问候/告别/感谢识别"""
    patterns = (
        r'^(你好|您好|嗨|hi|hello|hey|早[上啊]|晚上好|下午好)',
        r'(再见|拜拜|bye|see you|下次见)',
        r'(谢谢|感谢|多谢|辛苦了|thank)',
        r'^(在吗|有人在吗|有人在么)',
    )
    return any(re.search(p, text.strip(), re.IGNORECASE) for p in patterns)


def _match_chit_chat(text: str) -> bool:
    """闲聊识别"""
    patterns = (
        r'(今天天气|天气怎么样|你叫什么|你几岁|你是谁)',
        r'(你会什么|你能做什么|你有什么功能)',
        r'(真棒|厉害|不错|很好|哈哈|呵呵)',
        r'(你觉得|你认为|你感觉)',
    )
    return any(re.search(p, text.strip(), re.IGNORECASE) for p in patterns)


def _match_clarification(text: str) -> bool:
    """追问/澄清识别"""
    patterns = (
        r'(什么意思|具体点|具体一点|详细说说|展开说说)',
        r'(能举个例子吗|举例说明|有没有例子)',
        r'(还有吗|继续说|然后呢|所以呢|接着说)',
        r'(没听懂|不理解|不明白|没明白|能解释一下)',
        r'(再|多|更)(具体|详细|深入)',
    )
    return any(re.search(p, text.strip(), re.IGNORECASE) for p in patterns)


def _match_tool_operation(text: str) -> bool:
    """工具/系统操作类问题识别"""
    patterns = (
        r'(怎么用|用法|怎么操作|操作步骤)',
        r'(搜索|查找|找一下|查一下|读一下|读取).*(页面|文件|文档)',
        r'(新建|创建|删除|修改|更新).*(页面|文件|会话)',
    )
    return any(re.search(p, text.strip(), re.IGNORECASE) for p in patterns)


def _match_knowledge_query(text: str) -> bool:
    """知识查询识别——含提问词或明显的信息索取"""
    patterns = (
        r'(什么|什么是|怎么样|如何|为什么|怎么|多少|几个)',
        r'(能告诉我|请教|请问|问一下|想问|我想知道|我想了解|介绍一下)',
        r'(定义|概念|原理|区别|对比|关系|关联|联系)',
    )
    return bool(re.search(r'[?？]', text)) or any(
        re.search(p, text.strip(), re.IGNORECASE) for p in patterns
    )


# ── 规则分类 ──────────────────────────────────────────────────────────────────


def classify_intent(text: str) -> dict[str, Any]:
    """规则驱动的用户意图分类

    Args:
        text: 用户输入的文本

    Returns:
        {"category": str, "confidence": float, "explanation": str}

    分类优先级（先匹配先返回）：
      greeting → clarification → tool_operation → knowledge_query → chit_chat → general_query → unknown
    """
    stripped = text.strip()
    if not stripped:
        return {
            "category": C.INTENT_UNKNOWN,
            "confidence": 0.0,
            "explanation": "空输入",
        }

    # 1. 问候/告别/感谢
    if _match_greeting(stripped):
        return {
            "category": C.INTENT_GREETING,
            "confidence": C.INTENT_CONFIDENCE_HIGH,
            "explanation": "匹配问候/告别/感谢关键词",
        }

    # 2. 追问/澄清
    if _match_clarification(stripped):
        return {
            "category": C.INTENT_CLARIFICATION,
            "confidence": C.INTENT_CONFIDENCE_MEDIUM,
            "explanation": "匹配追问/澄清关键词",
        }

    # 3. 工具操作
    if _match_tool_operation(stripped):
        return {
            "category": C.INTENT_TOOL_OPERATION,
            "confidence": C.INTENT_CONFIDENCE_MEDIUM,
            "explanation": "匹配工具操作关键词",
        }

    # 4. 知识查询
    if _match_knowledge_query(stripped):
        return {
            "category": C.INTENT_KNOWLEDGE_QUERY,
            "confidence": C.INTENT_CONFIDENCE_HIGH,
            "explanation": "匹配知识查询关键词或问号",
        }

    # 5. 闲聊
    if _match_chit_chat(stripped):
        return {
            "category": C.INTENT_CHIT_CHAT,
            "confidence": C.INTENT_CONFIDENCE_MEDIUM,
            "explanation": "匹配闲聊关键词",
        }

    # 6. 回退：含中文 + 一定长度 → general_query
    if _has_chinese(stripped) and len(stripped) >= 4:
        return {
            "category": C.INTENT_GENERAL_QUERY,
            "confidence": C.INTENT_CONFIDENCE_LOW,
            "explanation": "未匹配特定模式，默认归类为 general_query",
        }

    return {
        "category": C.INTENT_UNKNOWN,
        "confidence": C.INTENT_CONFIDENCE_LOW,
        "explanation": "未能识别意图模式",
    }


# ── LLM 兜底分类 ────────────────────────────────────────────────────────────


def _classify_with_llm(text: str, llm) -> dict[str, Any]:
    """用 LLM 结构化输出做意图分类

    Args:
        text: 用户输入
        llm: ChatOpenAI 实例

    Returns:
        {"category": str, "confidence": float, "explanation": str}
    """
    from src.agent.planning.prompt import INTENT_CLASSIFICATION_PROMPT, IntentClassificationResult
    from langchain_core.messages import SystemMessage, HumanMessage

    structured_llm = llm.with_structured_output(IntentClassificationResult)
    result: IntentClassificationResult = structured_llm.invoke([
        SystemMessage(content=INTENT_CLASSIFICATION_PROMPT),
        HumanMessage(content=f"用户输入: {text}"),
    ])

    return {
        "category": result.category,
        "confidence": result.confidence,
        "explanation": result.explanation,
    }


# ── 子类目 → 顶层意图映射 ──────────────────────────────────────────────────


def _resolve_top_intent(category: str) -> str:
    """将细粒度分类映射为顶层意图（对应图路由）

    Args:
        category: 子类目（INTENT_GREETING / INTENT_KNOWLEDGE_QUERY 等）

    Returns:
        INTENT_SEARCH / INTENT_CHAT / INTENT_ADMIN / INTENT_TOOL
    """
    return C.INTENT_CATEGORY_MAP.get(category, C.INTENT_SEARCH)


# ── 统一入口 ──────────────────────────────────────────────────────────────


def classify_user_intent(text: str, llm=None) -> dict[str, Any]:
    """分类用户意图（规则 + LLM 兜底）

    流程：
      1. 规则匹配（最快路径，无 LLM 开销）
      2. LLM 结构化分类（仅规则未匹配且 llm 参数提供时）
      3. 默认降级为 general_query

    Args:
        text: 用户输入文本
        llm: 可选 ChatOpenAI，用于 LLM 兜底

    Returns:
        {"category": str, "confidence": float, "explanation": str, "top_intent": str}
    """
    # 1. 规则匹配
    result = classify_intent(text)
    if result["category"] != C.INTENT_UNKNOWN:
        result["top_intent"] = _resolve_top_intent(result["category"])
        logger.debug("意图分类（规则）| category=%s top=%s confidence=%.2f",
                     result["category"], result["top_intent"], result["confidence"])
        return result

    # 2. LLM 兜底
    if llm is not None:
        try:
            llm_result = _classify_with_llm(text, llm)
            llm_result["top_intent"] = _resolve_top_intent(llm_result["category"])
            logger.debug("意图分类（LLM）| category=%s top=%s confidence=%.2f",
                         llm_result["category"], llm_result["top_intent"], llm_result["confidence"])
            return llm_result
        except Exception as e:
            logger.warning("LLM 意图分类失败，降级 | error=%s", e)

    # 3. 默认降级
    logger.debug("意图分类（默认）| category=general_query top=search")
    return {
        "category": C.INTENT_GENERAL_QUERY,
        "confidence": C.INTENT_CONFIDENCE_LOW,
        "explanation": "规则未匹配，默认降级",
        "top_intent": C.INTENT_SEARCH,
    }


# ── LangGraph 图节点函数 ─────────────────────────────────────────────────


def intent_classifier_node(state: dict) -> dict:
    """意图分类图节点

    在 call_model 之前运行，从最新用户消息中提取意图，
    存入 AgentState.current_intent 供后续路由使用。

    规则匹配优先，不依赖 LLM（零额外延迟）。
    即使分类失败也不阻断流程——默认 search 让 agent 自行处理。

    Args:
        state: AgentState

    Returns:
        {"current_intent": str} 或 {}（无用户消息时）
    """
    messages = state.get(C.STATE_MESSAGES, [])
    if not messages:
        return {}

    # 找最后一轮用户消息
    user_text = ""
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "human":
            user_text = str(getattr(msg, "content", "") or "")
            break

    if not user_text:
        return {}

    # 只做规则分类（图节点运行在主线程，避免 LLM 阻塞）
    result = classify_intent(user_text)

    # 写入顶级意图
    top_intent = result.get("top_intent", result["category"])
    logger.info("意图分类 | category=%s top_intent=%s confidence=%.2f",
                result["category"], top_intent, result["confidence"])
    return {C.STATE_INTENT: top_intent}
