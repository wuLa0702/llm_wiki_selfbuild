"""
执行模块 — 响应格式化与结构化提取

职责：
  - 定义 AgentResponse 结构化输出模型
  - 将 LLM 的文本回答提取为结构化格式（引用页面、追问建议）
  - LLM 调用失败时降级为纯文本
"""

import logging

from langchain_core.messages import HumanMessage, SystemMessage as SysMsg
from pydantic import BaseModel, Field

from src.agent import constants as C

logger = logging.getLogger("agent.response")


# ── 结构化输出模型 ──────────────────────────────────────────────────────────


class AgentResponse(BaseModel):
    """Agent 最终回答的结构化输出

    当 LLM 不调用工具、直接回答时，
    用 with_structured_output 提取引用页面和追问建议。
    """
    answer: str = Field(description="Agent 的回答正文")
    cited_pages: list[str] = Field(description="回答中引用的 Wiki 页面路径列表", default=[])
    follow_up_questions: list[str] = Field(description="基于当前回答建议的追问话题", default=[])


# ── 结构化提取提示词 ──────────────────────────────────────────────────────

STRUCTURED_EXTRACTION_SYSTEM_PROMPT = (
    "从以下 Agent 回答中提取：\n"
    "1. 引用的 Wiki 页面路径（格式如 entities/python.md）\n"
    "2. 建议的追问问题\n\n"
    "如果回答中没有引用任何页面，cited_pages 返回空列表。"
    "如果没有明显的追问方向，follow_up_questions 返回空列表。"
)


# ── 引用富化 ────────────────────────────────────────────────────────────────


def enrich_cited_pages(paths: list[str]) -> list[dict]:
    """将引用的 Wiki 页面路径富化为带元数据的对象

    查询 WikiRepository 获取每个页面的标题和类型，
    页面不存在或查询失败时降级为 {path, title: 文件名, page_type: unknown}。

    Args:
        paths: 页面路径列表，如 ["entities/python.md"]

    Returns:
        [{"path": str, "title": str, "page_type": str}, ...]
    """
    from pathlib import Path

    from src.db.repository import WikiRepository

    enriched: list[dict] = []
    try:
        repo = WikiRepository()
        for p in paths:
            meta = repo.get_page(p)
            enriched.append({
                C.FIELD_CITATION_PATH: p,
                C.FIELD_CITATION_TITLE: (meta.get("title") or Path(p).stem) if meta else Path(p).stem,
                C.FIELD_CITATION_PAGE_TYPE: (meta.get("page_type") or C.DEFAULT_PAGE_TYPE) if meta else C.DEFAULT_PAGE_TYPE,
            })
    except Exception:
        # 元数据查询失败时降级为纯路径列表（向后兼容）
        enriched = [p for p in paths]
    return enriched


# ── 格式化 ──────────────────────────────────────────────────────────────────


def format_response(content: str, llm=None) -> AgentResponse:
    """对 Agent 的文本回答做结构化提取

    在 agent 回答后用 with_structured_output 提取 cited_pages 和 follow_up_questions。
    提取失败时降级为仅保留 answer 文本。

    Args:
        content: Agent 的 AIMessage.content
        llm: 可选的 LLM 实例，不传时使用默认 llm（需从 planning.graph 导入）

    Returns:
        AgentResponse(answer, cited_pages, follow_up_questions)
    """
    if llm is None:
        from src.agent.planning.graph import llm as default_llm
        llm = default_llm

    try:
        structured_llm = llm.with_structured_output(AgentResponse)
        result = structured_llm.invoke([
            SysMsg(content=STRUCTURED_EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=content),
        ])
        return result
    except Exception as e:
        logger.warning("Agent 响应结构化提取失败 | error=%s", e)
        return AgentResponse(answer=content, cited_pages=[], follow_up_questions=[])
