"""
LLM 适配器 — 统一模型调用接口
支持多 Provider（DeepSeek / 豆包 / OpenAI / Claude）
"""


class LLMAdapter:
    """统一的 LLM 模型适配器，支持切换 Provider"""

    def __init__(self, provider: str = "deepseek"):
        self.provider = provider

    def chat(self, prompt: str, system_prompt: str = "") -> str:
        """
        调用 LLM 模型
        Args:
            prompt: 用户提示
            system_prompt: 系统提示词
        Returns:
            模型回复文本
        """
        raise NotImplementedError("Phase 1 实现")

    def chat_structured(self, prompt: str, schema: dict) -> dict:
        """调用 LLM 并返回结构化输出（JSON Schema）"""
        raise NotImplementedError("Phase 2 实现")
