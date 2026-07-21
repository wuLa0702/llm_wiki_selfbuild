"""
LLM 适配器单元测试

运行说明:
  pytest tests/test_llm/ -v                 # 全部（Mock + 真实调用）
  pytest tests/test_llm/ -v -m "not real"   # 只看 Mock 测试（不花 API 费用）
  pytest tests/test_llm/ -v -s -m real      # 只看真实调用，显示回复内容
"""
import os

import pytest

from src.llm.adapter import LLMAdapter, LLMError


# ============================================================================
# 正常路径 — DeepSeek
# ============================================================================


def test_chat_returns_string(mocker):
    """有效 prompt 返回模型回复文本"""
    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.return_value = mocker.MagicMock(content="Hello, world!")
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")
    result = adapter.chat("Hi there")

    assert result == "Hello, world!"
    assert adapter.provider == "deepseek"
    mock_llm_instance.invoke.assert_called_once()


def test_chat_with_system_prompt(mocker):
    """system_prompt 作为 SystemMessage 传递给 LLM"""
    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.return_value = mocker.MagicMock(content="Ok")
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")
    adapter.chat("User question", system_prompt="Be helpful.")

    call_args = mock_llm_instance.invoke.call_args[0][0]
    assert len(call_args) == 2
    assert call_args[0].type == "system"
    assert call_args[0].content == "Be helpful."
    assert call_args[1].type == "human"
    assert call_args[1].content == "User question"


def test_chat_without_system_prompt(mocker):
    """system_prompt 为空时只传 HumanMessage"""
    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.return_value = mocker.MagicMock(content="Ok")
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")
    adapter.chat("Just a user message")

    call_args = mock_llm_instance.invoke.call_args[0][0]
    assert len(call_args) == 1
    assert call_args[0].type == "human"


# ============================================================================
# chat_template — ChatPromptTemplate 支持
# ============================================================================


def test_chat_template_returns_string(mocker):
    """chat_template 使用模板变量生成消息并返回结果"""
    from langchain_core.prompts import ChatPromptTemplate

    template = ChatPromptTemplate.from_messages([
        ("system", "You are {role}."),
        ("human", "Tell me about {topic}"),
    ])

    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.return_value = mocker.MagicMock(content="Result")
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")
    result = adapter.chat_template(template, role="teacher", topic="Python")

    assert result == "Result"
    call_messages = mock_llm_instance.invoke.call_args[0][0]
    assert len(call_messages) == 2
    assert "teacher" in call_messages[0].content
    assert "Python" in call_messages[1].content


def test_chat_template_missing_variable_raises(mocker):
    """缺少模板变量时 LangChain 抛出 KeyError"""
    from langchain_core.prompts import ChatPromptTemplate

    template = ChatPromptTemplate.from_messages([
        ("human", "Topic: {topic}"),
    ])

    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})
    adapter = LLMAdapter("deepseek")

    with pytest.raises(KeyError):
        adapter.chat_template(template)


def test_chat_template_empty_rendered_raises(mocker):
    """模板渲染为空时抛出 ValueError"""
    from langchain_core.prompts import ChatPromptTemplate

    template = ChatPromptTemplate.from_messages([
        ("system", ""),
        ("human", ""),
    ])

    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})
    adapter = LLMAdapter("deepseek")

    with pytest.raises(ValueError, match="empty"):
        adapter.chat_template(template)


def test_chat_template_llm_error(mocker):
    """模板调用 LLM 失败时抛 LLMError"""
    from langchain_core.prompts import ChatPromptTemplate

    template = ChatPromptTemplate.from_messages([
        ("human", "Hello"),
    ])

    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.side_effect = Exception("Boom")
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")

    with pytest.raises(LLMError, match="LLM call failed"):
        adapter.chat_template(template)


# ============================================================================
# 边界条件 — DeepSeek
# ============================================================================


def test_chat_empty_prompt_raises(mocker):
    """空字符串 prompt 抛出 ValueError"""
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})
    adapter = LLMAdapter("deepseek")

    with pytest.raises(ValueError, match="must not be empty"):
        adapter.chat("")

    with pytest.raises(ValueError, match="must not be empty"):
        adapter.chat("   ")


def test_chat_whitespace_prompt_raises(mocker):
    """纯空白 prompt 抛出 ValueError"""
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})
    adapter = LLMAdapter("deepseek")

    with pytest.raises(ValueError, match="must not be empty"):
        adapter.chat("\n\t  ")


def test_init_missing_api_key(mocker):
    """API Key 缺失时抛出 ValueError（DeepSeek）"""
    mocker.patch.dict(os.environ, {}, clear=True)

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        LLMAdapter("deepseek")


def test_init_reads_model_from_env(mocker):
    """从环境变量读取 DEEPSEEK_MODEL"""
    mock_llm_class = mocker.patch("src.llm.adapter.ChatOpenAI")
    mock_llm_instance = mocker.MagicMock()
    mock_llm_class.return_value = mock_llm_instance
    mock_llm_instance.invoke.return_value = mocker.MagicMock(content="ok")
    mocker.patch.dict(
        os.environ,
        {
            "DEEPSEEK_API_KEY": "test-key",
            "DEEPSEEK_MODEL": "deepseek-v4-flash",
            "DEEPSEEK_API_BASE": "https://api.deepseek.com/v1",
        },
    )

    LLMAdapter("deepseek")

    mock_llm_class.assert_called_once_with(
        model="deepseek-v4-flash",
        api_key="test-key",
        base_url="https://api.deepseek.com/v1",
        timeout=120,
        max_retries=0,
    )


def test_init_reads_env_vars(mocker):
    """自定义环境变量正确传递给 ChatOpenAI（DeepSeek）"""
    mock_llm_class = mocker.patch("src.llm.adapter.ChatOpenAI")
    mock_llm_instance = mocker.MagicMock()
    mock_llm_class.return_value = mock_llm_instance
    mock_llm_instance.invoke.return_value = mocker.MagicMock(content="ok")
    mocker.patch.dict(
        os.environ,
        {
            "DEEPSEEK_API_KEY": "sk-custom",
            "DEEPSEEK_API_BASE": "https://custom.api.com/v1",
            "DEEPSEEK_MODEL": "custom-model",
        },
    )

    LLMAdapter("deepseek")

    mock_llm_class.assert_called_once_with(
        model="custom-model",
        api_key="sk-custom",
        base_url="https://custom.api.com/v1",
        timeout=120,
        max_retries=0,
    )


# ============================================================================
# 边界条件 — 豆包
# ============================================================================


def test_init_doubao_provider(mocker):
    """传入 provider='doubao' 时读取 ARK_API_KEY 等环境变量"""
    mock_llm_class = mocker.patch("src.llm.adapter.ChatOpenAI")
    mock_llm_instance = mocker.MagicMock()
    mock_llm_class.return_value = mock_llm_instance
    mock_llm_instance.invoke.return_value = mocker.MagicMock(content="ok")
    mocker.patch.dict(
        os.environ,
        {
            "ARK_API_KEY": "ark-test-key",
            "ARK_API_BASE": "https://custom.ark.com/v3",
            "ARK_MODEL_CHAT": "ep-custom",
        },
    )

    adapter = LLMAdapter("doubao")

    assert adapter.provider == "doubao"
    mock_llm_class.assert_called_once_with(
        model="ep-custom",
        api_key="ark-test-key",
        base_url="https://custom.ark.com/v3",
        timeout=120,
        max_retries=0,
    )


def test_init_doubao_defaults(mocker):
    """豆包使用默认值当 env vars 缺失"""
    mock_llm_class = mocker.patch("src.llm.adapter.ChatOpenAI")
    mock_llm_instance = mocker.MagicMock()
    mock_llm_class.return_value = mock_llm_instance
    mock_llm_instance.invoke.return_value = mocker.MagicMock(content="ok")
    mocker.patch.dict(os.environ, {"ARK_API_KEY": "ark-key"})

    LLMAdapter("doubao")

    mock_llm_class.assert_called_once_with(
        model="ep-20260704205018-srlpk",
        api_key="ark-key",
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        timeout=120,
        max_retries=0,
    )


def test_init_doubao_missing_api_key(mocker):
    """ARK_API_KEY 缺失时抛出 ValueError"""
    mocker.patch.dict(os.environ, {}, clear=True)

    with pytest.raises(ValueError, match="ARK_API_KEY"):
        LLMAdapter("doubao")


# ============================================================================
# 边界条件 — 通用
# ============================================================================


def test_init_unknown_provider_raises():
    """不支持的 provider 抛出 ValueError 并列出可用选项"""
    with pytest.raises(ValueError, match="Unsupported provider") as exc_info:
        LLMAdapter("unknown")

    assert "deepseek" in str(exc_info.value)
    assert "doubao" in str(exc_info.value)


def test_init_reads_default_provider_from_env(mocker):
    """不传 provider 时从 LLM_PROVIDER 环境变量读取"""
    mock_llm_class = mocker.patch("src.llm.adapter.ChatOpenAI")
    mock_llm_instance = mocker.MagicMock()
    mock_llm_class.return_value = mock_llm_instance
    mock_llm_instance.invoke.return_value = mocker.MagicMock(content="ok")
    mocker.patch.dict(
        os.environ,
        {"LLM_PROVIDER": "deepseek", "DEEPSEEK_API_KEY": "sk-test"},
    )

    adapter = LLMAdapter()
    assert adapter.provider == "deepseek"


# ============================================================================
# chat_structured — 结构化 JSON 输出
# ============================================================================


def test_chat_structured_returns_dict(mocker):
    """chat_structured 调用 LLM 并返回解析后的 dict"""
    mocker.patch("src.llm.adapter.ChatOpenAI").return_value.invoke.return_value = (
        mocker.MagicMock(content='{"key": "value"}')
    )
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")
    result = adapter.chat_structured(prompt="Give me JSON")

    assert isinstance(result, dict)
    assert result == {"key": "value"}


def test_chat_structured_with_code_block(mocker):
    """LLM 返回 ```json``` 代码块中的 JSON 也能解析"""
    mocker.patch("src.llm.adapter.ChatOpenAI").return_value.invoke.return_value = (
        mocker.MagicMock(content='```json\n{"a": 1}\n```')
    )
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")
    result = adapter.chat_structured(prompt="Give me JSON")
    assert result == {"a": 1}


def test_chat_structured_empty_prompt_raises(mocker):
    """空 prompt 抛出 ValueError"""
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})
    adapter = LLMAdapter("deepseek")

    with pytest.raises(ValueError, match="must not be empty"):
        adapter.chat_structured("")


def test_chat_structured_invalid_json_raises(mocker):
    """LLM 返回无效 JSON 时抛出 LLMError"""
    mocker.patch("src.llm.adapter.ChatOpenAI").return_value.invoke.return_value = (
        mocker.MagicMock(content="not json at all")
    )
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")
    with pytest.raises(LLMError, match="Failed to parse"):
        adapter.chat_structured(prompt="Give me JSON")


def test_chat_structured_api_error_raises(mocker):
    """API 调用失败抛出 LLMError"""
    mocker.patch("src.llm.adapter.ChatOpenAI").return_value.invoke.side_effect = (
        Exception("connection refused")
    )
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")
    with pytest.raises(LLMError, match="LLM call failed"):
        adapter.chat_structured(prompt="Hello")


# ============================================================================
# 错误路径 — LLM 异常
# ============================================================================


def test_chat_api_timeout(mocker):
    """API 超时被捕获并重新抛为 LLMError"""
    from openai import APITimeoutError

    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.side_effect = APITimeoutError("Request timed out")
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")

    with pytest.raises(LLMError, match="LLM call failed"):
        adapter.chat("Hello")


def test_chat_api_connection_error(mocker):
    """连接错误被捕获并重新抛为 LLMError"""
    import httpx
    from openai import APIConnectionError

    mock_request = httpx.Request("GET", "https://api.deepseek.com/v1")
    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.side_effect = APIConnectionError(
        message="Connection refused", request=mock_request
    )
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")

    with pytest.raises(LLMError, match="LLM call failed"):
        adapter.chat("Hello")


def test_chat_rate_limit_error(mocker):
    """频率限制错误被捕获并重新抛为 LLMError"""
    import httpx
    from openai import RateLimitError

    mock_request = httpx.Request("GET", "https://api.deepseek.com/v1")
    mock_response = httpx.Response(status_code=429, request=mock_request)
    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.side_effect = RateLimitError(
        message="Rate limit exceeded", response=mock_response, body=None
    )
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")

    with pytest.raises(LLMError, match="LLM call failed"):
        adapter.chat("Hello")


# ============================================================================
# Token 用量提取
# ============================================================================


def test_chat_records_token_usage(mocker):
    """chat() 后 _last_usage 包含 token 用量"""
    mock_response = mocker.MagicMock()
    mock_response.response_metadata = {
        "token_usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        },
    }
    mock_response.content = "Hello, world!"
    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.return_value = mock_response
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")
    adapter.chat("Hi there")

    assert adapter.last_usage is not None
    assert adapter.last_usage["input_tokens"] == 100
    assert adapter.last_usage["output_tokens"] == 50
    assert adapter.last_usage["total_tokens"] == 150
    assert adapter.last_usage["model"] == "deepseek-v4-flash"  # 默认值
    assert "timestamp" in adapter.last_usage


def test_chat_no_token_usage_graceful(mocker):
    """response_metadata 不含 token_usage 时不抛异常，_last_usage 保持 None 或未设置"""
    mock_response = mocker.MagicMock()
    mock_response.response_metadata = {}  # 空的 metadata
    mock_response.content = "No usage info"
    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.return_value = mock_response
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")
    adapter.chat("Hi")

    assert adapter.last_usage is None


def test_chat_template_records_token_usage(mocker):
    """chat_template() 后 _last_usage 正确填充"""
    from langchain_core.prompts import ChatPromptTemplate

    template = ChatPromptTemplate.from_messages([
        ("human", "Question: {q}"),
    ])

    mock_response = mocker.MagicMock()
    mock_response.response_metadata = {
        "token_usage": {
            "prompt_tokens": 80,
            "completion_tokens": 30,
            "total_tokens": 110,
        },
    }
    mock_response.content = "42"
    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.return_value = mock_response
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter("deepseek")
    adapter.chat_template(template, q="meaning of life?")

    assert adapter.last_usage is not None
    assert adapter.last_usage["total_tokens"] == 110


# ============================================================================
# 真实 API 调用测试（需要 .env 中配置对应的 API Key）
# ============================================================================


@pytest.mark.real
def test_real_deepseek_chat():
    """真实调用 DeepSeek — 简单对话"""
    from dotenv import load_dotenv

    load_dotenv()

    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY 未设置，跳过真实调用测试")

    adapter = LLMAdapter("deepseek")
    result = adapter.chat("用一句话介绍 Python 语言")

    assert isinstance(result, str)
    assert len(result) > 0
    print(f"\n[DeepSeek 真实调用] 回复: {result}")


@pytest.mark.real
def test_real_deepseek_system_prompt():
    """真实调用 DeepSeek — 带 System Prompt"""
    from dotenv import load_dotenv

    load_dotenv()

    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY 未设置，跳过真实调用测试")

    adapter = LLMAdapter("deepseek")
    result = adapter.chat(
        prompt="1 + 1 = ?",
        system_prompt="你是一个数学老师，请用中文回答，只给答案。",
    )

    assert isinstance(result, str)
    assert len(result) > 0
    print(f"\n[DeepSeek 真实调用] 数学老师回复: {result}")


@pytest.mark.real
def test_real_deepseek_long():
    """真实调用 DeepSeek — 生成长文本"""
    from dotenv import load_dotenv

    load_dotenv()

    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY 未设置，跳过真实调用测试")

    adapter = LLMAdapter("deepseek")
    result = adapter.chat("请用中文写一段约100字的自我介绍，你是 LLM Wiki 知识库助手")

    assert isinstance(result, str)
    assert len(result) > 50
    print(f"\n[DeepSeek 真实调用] 回复长度: {len(result)} 字符\n内容: {result}")


@pytest.mark.real
def test_real_doubao_chat():
    """真实调用豆包 — 简单对话"""
    from dotenv import load_dotenv

    load_dotenv()

    if not os.environ.get("ARK_API_KEY"):
        pytest.skip("ARK_API_KEY 未设置，跳过真实调用测试")

    adapter = LLMAdapter("doubao")
    result = adapter.chat("用一句话介绍你自己")

    assert isinstance(result, str)
    assert len(result) > 0
    print(f"\n[豆包 真实调用] 回复: {result}")


@pytest.mark.real
def test_real_doubao_system_prompt():
    """真实调用豆包 — 带 System Prompt"""
    from dotenv import load_dotenv

    load_dotenv()

    if not os.environ.get("ARK_API_KEY"):
        pytest.skip("ARK_API_KEY 未设置，跳过真实调用测试")

    adapter = LLMAdapter("doubao")
    result = adapter.chat(
        prompt="1 + 1 = ?",
        system_prompt="你是一个数学老师，请用中文回答，只给答案。",
    )

    assert isinstance(result, str)
    assert len(result) > 0
    print(f"\n[豆包 真实调用] 数学老师回复: {result}")
