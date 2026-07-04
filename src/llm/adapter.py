"""
LLM 适配器 — 统一模型调用接口
支持多 Provider（DeepSeek / 豆包 / OpenAI / Claude）
"""
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.core.logging_config import get_logger

load_dotenv()

logger = get_logger("adapter")


class LLMError(Exception):
    """LLM 适配器基础异常"""


class LLMAdapter:
    """统一的 LLM 模型适配器，支持切换 Provider"""

    def __init__(self, provider: str = "deepseek") -> None:
        """
        初始化 LLM 适配器

        Args:
            provider: LLM Provider 标识（默认 deepseek）

        Raises:
            ValueError: DEEPSEEK_API_KEY 未设置时抛出
        """
        self.provider = provider

        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            logger.error("DEEPSEEK_API_KEY 未设置")
            raise ValueError(
                "DEEPSEEK_API_KEY is not set in environment. "
                "Copy .env.example to .env and fill in your API key."
            )

        model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        base_url = os.environ.get("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")

        self._llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout=30,
            max_retries=2,
        )

        logger.info(
            "LLMAdapter 初始化完成 | provider=%s model=%s base_url=%s",
            provider,
            model,
            base_url,
        )

    def chat(self, prompt: str, system_prompt: str = "") -> str:
        """
        调用 LLM 模型

        Args:
            prompt: 用户提示
            system_prompt: 系统提示词

        Returns:
            模型回复文本

        Raises:
            ValueError: prompt 为空时抛出
            LLMError: API 调用失败时抛出
        """
        if not prompt or not prompt.strip():
            logger.warning("chat 调用被拒绝：prompt 为空")
            raise ValueError("Prompt must not be empty")

        logger.debug(
            "chat 开始 | prompt_len=%d system_prompt_len=%d",
            len(prompt),
            len(system_prompt),
        )

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        try:
            response = self._llm.invoke(messages)
        except Exception as exc:
            logger.error(
                "chat 失败 | provider=%s error=%s", self.provider, exc
            )
            raise LLMError(
                f"LLM call failed for provider '{self.provider}': {exc}"
            ) from exc

        content = response.content if hasattr(response, "content") else str(response)
        logger.info(
            "chat 成功 | output_len=%d",
            len(content),
        )
        return content

    def chat_structured(self, prompt: str, schema: dict) -> dict:
        """调用 LLM 并返回结构化输出（JSON Schema）"""
        logger.warning("chat_structured 被调用，但尚未实现（Phase 2）")
        raise NotImplementedError("Phase 2 实现")
