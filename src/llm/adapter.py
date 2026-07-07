"""
LLM 适配器 — 统一模型调用接口
支持多 Provider（DeepSeek / 豆包 / OpenAI / Claude）
"""
import os
from datetime import datetime

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

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
        "default_model": "deepseek-v4-flash",
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

    def __init__(
        self, provider: str | None = None, token_tracker: object | None = None
    ) -> None:
        """
        初始化 LLM 适配器

        Args:
            provider: LLM Provider 标识（deepseek / doubao）。
                      不传则取环境变量 LLM_PROVIDER，默认 deepseek。
            token_tracker: 可选的 TokenTracker 实例（Phase 3 注入）。

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

        self._model_name = model
        self._last_usage: dict | None = None
        self._token_tracker = token_tracker

        self._llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            timeout=15,
            max_retries=1,
        )

        logger.info(
            "LLMAdapter 初始化完成 | provider=%s model=%s base_url=%s",
            provider,
            model,
            base_url,
        )

    @property
    def last_usage(self) -> dict | None:
        """最近一次 LLM 调用的 token 用量"""
        return self._last_usage

    def _record_usage(self, operation: str, response) -> None:
        """
        从 LLM 响应中提取 token 用量并记录

        Args:
            operation: 操作类型标识（chat / chat_template / chat_structured）
            response: LLM 返回的 AIMessage 对象
        """
        meta = getattr(response, "response_metadata", {}) or {}
        usage = meta.get("token_usage", {})
        if not usage:
            return

        self._last_usage = {
            "input_tokens": usage["prompt_tokens"],
            "output_tokens": usage["completion_tokens"],
            "total_tokens": usage["total_tokens"],
            "model": self._model_name,
            "timestamp": datetime.now().isoformat(),
        }

        if self._token_tracker:
            self._token_tracker.record(operation, self._last_usage)

        logger.debug(
            "token_usage recorded | operation=%s input=%d output=%d total=%d",
            operation,
            usage["prompt_tokens"],
            usage["completion_tokens"],
            usage["total_tokens"],
        )

    def chat(self, prompt: str, system_prompt: str = "", operation: str = "chat") -> str:
        """
        调用 LLM 模型

        Args:
            prompt: 用户提示
            system_prompt: 系统提示词
            operation: 业务操作标识（如 query_suggest_pages, overview），
                       用于 token 用量追踪

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
            "chat 开始 | provider=%s prompt_len=%d system_prompt_len=%d operation=%s",
            self.provider,
            len(prompt),
            len(system_prompt),
            operation,
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

        self._record_usage(operation, response)

        content = response.content if hasattr(response, "content") else str(response)
        logger.info(
            "chat 成功 | provider=%s output_len=%d",
            self.provider,
            len(content),
        )
        return content

    def chat_template(self, template: ChatPromptTemplate, operation: str = "chat_template", **kwargs: str) -> str:
        """
        使用 ChatPromptTemplate 调用 LLM

        模板变量通过 kwargs 传入，自动填充。
        变量缺失时 LangChain 会抛出 KeyError。

        Args:
            template: ChatPromptTemplate 实例
            operation: 业务操作标识（如 ingest_step2），用于 token 用量追踪
            **kwargs: 模板变量名和值

        Returns:
            模型回复文本

        Raises:
            LLMError: API 调用失败时抛出
            ValueError: prompt 为空时抛出
        """
        messages = template.format_messages(**kwargs)

        # 校验非空
        all_text = " ".join(m.content for m in messages if hasattr(m, "content"))
        if not all_text.strip():
            raise ValueError("Template rendered empty prompt")

        logger.debug(
            "chat_template 开始 | provider=%s messages=%d operation=%s",
            self.provider,
            len(messages),
            operation,
        )

        try:
            response = self._llm.invoke(messages)
        except Exception as exc:
            logger.error(
                "chat_template 失败 | provider=%s error=%s", self.provider, exc
            )
            raise LLMError(
                f"LLM call failed for provider '{self.provider}': {exc}"
            ) from exc

        self._record_usage(operation, response)

        content = response.content if hasattr(response, "content") else str(response)
        logger.info(
            "chat_template 成功 | provider=%s output_len=%d",
            self.provider,
            len(content),
        )
        return content

    def chat_structured(
        self,
        prompt: str,
        system_prompt: str = "",
        output_schema: type[BaseModel] | None = None,
        operation: str = "chat_structured",
    ) -> dict:
        """
        调用 LLM 并返回结构化输出（JSON）

        使用 LangChain JsonOutputParser：
          1. 自动注入格式说明到 prompt
          2. 调用 LLM
          3. 解析 JSON（支持 ```json``` 代码块）
          4. Pydantic 校验（如果提供 output_schema）

        Args:
            prompt: 用户提示
            system_prompt: 系统提示词
            output_schema: 可选的 Pydantic 模型类，用于校验输出
            operation: 业务操作标识（如 query_synthesize, ingest_step1），
                       用于 token 用量追踪

        Returns:
            解析后的 dict

        Raises:
            ValueError: prompt 为空
            LLMError: API 调用失败或 JSON 解析失败
        """
        if not prompt or not prompt.strip():
            raise ValueError("Prompt must not be empty")

        parser = JsonOutputParser(pydantic_object=output_schema)
        format_instructions = parser.get_format_instructions()
        full_prompt = f"{prompt}\n\n{format_instructions}"

        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=full_prompt))

        logger.debug(
            "chat_structured 开始 | provider=%s schema=%s operation=%s",
            self.provider,
            output_schema.__name__ if output_schema else "dict",
            operation,
        )

        try:
            response = self._llm.invoke(messages)
        except Exception as exc:
            logger.error(
                "chat_structured 调用失败 | provider=%s error=%s",
                self.provider, exc,
            )
            raise LLMError(
                f"LLM call failed for provider '{self.provider}': {exc}"
            ) from exc

        # 先记录 token 用量，再解析 JSON（解析失败也要记录）
        self._record_usage(operation, response)

        content = response.content if hasattr(response, "content") else str(response)

        try:
            result = parser.parse(content)
        except Exception as exc:
            logger.error(
                "chat_structured JSON 解析失败 | provider=%s error=%s",
                self.provider, exc,
            )
            raise LLMError(
                f"Failed to parse structured output for "
                f"provider '{self.provider}': {exc}"
            ) from exc

        logger.info(
            "chat_structured 成功 | provider=%s keys=%s",
            self.provider,
            list(result.keys()) if isinstance(result, dict) else "?",
        )
        return result
