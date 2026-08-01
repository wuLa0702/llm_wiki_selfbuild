"""
规划模块 — 系统提示词与结构化输出模型

职责：
  - 定义 Agent 的系统提示词（SYSTEM_PROMPT）
  - 定义结构化输出模型（AgentResponse, ReflectionResult, IntentClassificationResult）
  - 定义反思节点提示词（REFLECTION_SYSTEM_PROMPT）
  - 定义意图分类提示词（INTENT_CLASSIFICATION_PROMPT）
  - 与具体的图构建逻辑分离，方便独立修改
"""

from pydantic import BaseModel, Field


# ── 系统提示 ──────────────────────────────────────────────────────────────────

INTENT_CLASSIFICATION_PROMPT = """你是 LLM Wiki 的意图分类器。分析用户输入，分类其意图。

分类规则：
- greeting: 问候、告别、感谢、打招呼（不需要搜索知识库）
- knowledge_query: 询问知识库中的内容，需要搜索 Wiki 或读取页面来回答
- general_query: 通用问题，不依赖知识库内容（如"你怎么看"、"你好吗"）
- chit_chat: 闲聊、情感表达、无实质问题
- clarification: 追问、要求具体化、请求进一步解释
- tool_operation: 关于如何使用工具或系统的问题
- unknown: 无法确定

输出格式：category + confidence + explanation
"""


SYSTEM_PROMPT = """你是 LLM Wiki 的知识助手。你可以搜索、阅读、分析知识库中的内容来回答用户问题。

规则：
1. 回答必须基于 Wiki 页面内容，不要编造信息
2. 不确定时先调用 search_wiki 找到相关页面，再用 read_page 获取详情
3. 引用页面时使用 [[页面路径]] 格式，用户可点击跳转
4. 如果知识库中没有相关内容，明确告知用户，不要编造
5. 使用中文回答（除非用户用其他语言提问）
6. 回答要简洁准确，适当使用 Markdown 格式
7. 信息已足够回答时立即停止调用工具并直接回答；不要在已有充分答案后继续搜索或阅读"""


# ── 反思节点提示词 ──────────────────────────────────────────────────────────

REFLECTION_SYSTEM_PROMPT = """你是推理质量评估专家。分析以下对话片段中 Agent 的最后一次搜索/读取操作：

评估维度：
1. 这个搜索方向是否合理？是否用了正确的关键词？
2. 是否已经尝试过类似的搜索策略但没得到好结果？
3. 是否有更好的搜索策略或角度？

请结构化输出你的评估结果。"""


# ── 反思结构化输出模型 ──────────────────────────────────────────────────────


class IntentClassificationResult(BaseModel):
    """意图分类的结构化输出

    category:
      分类意图: "greeting" / "knowledge_query" / "general_query" / "chit_chat" / "clarification" / "tool_operation" / "unknown"
    confidence:
      置信度，0~1
    explanation:
      分类原因的简短解释
    """
    category: str = Field(description="意图类别")
    confidence: float = Field(description="置信度(0~1)", default=0.5)
    explanation: str = Field(description="分类原因", default="")


class ReflectionResult(BaseModel):
    """反思节点的结构化输出

    verdict:
      "proceed" — 搜索方向合理，继续当前思路
      "revise"  — 需要修正搜索策略
    revised_plan:
      当 verdict=revise 时，给出修正后的搜索计划（具体的关键词或方向）
    """
    verdict: str = Field(description="评估结论: 'proceed'（继续当前方向）或 'revise'（需要修正策略）")
    revised_plan: str = Field(description="当 verdict=revise 时，给出修正后的搜索或阅读策略", default="")
