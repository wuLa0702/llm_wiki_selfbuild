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

# ---------------------------------------------------------------------------
# Provider 注册表 — 新增 Provider 只需在此添加配置
# ---------------------------------------------------------------------------

PROVIDER_CONFIG: dict[str, dict[str, str]] = {
    "deepseek": {
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_API_BASE",
        "model_env": "DEEPSEEK_MODEL",
        "default_base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
    },
    "doubao": {
        "api_key_env": "ARK_API_KEY",
        "base_url_env": "ARK_API_BASE",
        "model_env": "ARK_MODEL_CHAT",
        "default_base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "ep-20260704205018-srlpk",
    },
}


class LLMError(Exception):
    """LLM 适配器基础异常"""


class LLMAdapter:
    """统一的 LLM 模型适配器，支持切换 Provider"""

    def __init__(self, provider: str | None = None) -> None:
        """
        初始化 LLM 适配器

        Args:
            provider: LLM Provider 标识（deepseek / doubao）。
                      不传则取环境变量 LLM_PROVIDER，默认 deepseek。

        Raises:
            ValueError: provider 不支持，或对应 API Key 未设置时抛出
        """
        if provider is None:
            provider = os.environ.get("LLM_PROVIDER", "deepseek")
        self.provider = provider

        config = PROVIDER_CONFIG.get(provider)
        if config is None:
            supported = ", ".join(PROVIDER_CONFIG.keys())
            raise ValueError(
                f"Unsupported provider '{provider}'. "
                f"Available: {supported}"
            )

        api_key = os.environ.get(config["api_key_env"])
        if not api_key:
            logger.error("%s 未设置", config["api_key_env"])
            raise ValueError(
                f"{config['api_key_env']} is not set in environment. "
                "Copy .env.example to .env and fill in your API key."
            )

        model = os.environ.get(config["model_env"], config["default_model"])
        base_url = os.environ.get(
            config["base_url_env"], config["default_base_url"]
        )

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
            "chat 开始 | provider=%s prompt_len=%d system_prompt_len=%d",
            self.provider,
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
            "chat 成功 | provider=%s output_len=%d",
            self.provider,
            len(content),
        )
        return content

    def chat_structured(self, prompt: str, schema: dict) -> dict:
        """调用 LLM 并返回结构化输出（JSON Schema）"""
        logger.warning("chat_structured 被调用，但尚未实现（Phase 2）")
        raise NotImplementedError("Phase 2 实现")
