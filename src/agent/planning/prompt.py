"""
规划模块 — 系统提示词与结构化输出模型

职责：
  - 定义 Agent 的系统提示词（SYSTEM_PROMPT）
  - 定义结构化输出模型（AgentResponse, ReflectionResult）
  - 定义反思节点提示词（REFLECTION_SYSTEM_PROMPT）
  - 与具体的图构建逻辑分离，方便独立修改
"""

from pydantic import BaseModel, Field


# ── 系统提示 ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """你是 LLM Wiki 的知识助手。你可以搜索、阅读、分析知识库中的内容来回答用户问题。

规则：
1. 回答必须基于 Wiki 页面内容，不要编造信息
2. 不确定时先调用 search_wiki 找到相关页面，再用 read_page 获取详情
3. 引用页面时使用 [[页面路径]] 格式，用户可点击跳转
4. 如果知识库中没有相关内容，明确告知用户，不要编造
5. 使用中文回答（除非用户用其他语言提问）
6. 回答要简洁准确，适当使用 Markdown 格式"""


# ── 反思节点提示词 ──────────────────────────────────────────────────────────

REFLECTION_SYSTEM_PROMPT = """你是推理质量评估专家。分析以下对话片段中 Agent 的最后一次搜索/读取操作：

评估维度：
1. 这个搜索方向是否合理？是否用了正确的关键词？
2. 是否已经尝试过类似的搜索策略但没得到好结果？
3. 是否有更好的搜索策略或角度？

请结构化输出你的评估结果。"""


# ── 反思结构化输出模型 ──────────────────────────────────────────────────────


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
