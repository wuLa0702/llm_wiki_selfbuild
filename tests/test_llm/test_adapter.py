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


# ---------------------------------------------------------------------------
# 正常路径
# ---------------------------------------------------------------------------


def test_chat_returns_string(mocker):
    """有效 prompt 返回模型回复文本"""
    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.return_value = mocker.MagicMock(content="Hello, world!")
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter()
    result = adapter.chat("Hi there")

    assert result == "Hello, world!"
    mock_llm_instance.invoke.assert_called_once()


def test_chat_with_system_prompt(mocker):
    """system_prompt 作为 SystemMessage 传递给 LLM"""
    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.return_value = mocker.MagicMock(content="Ok")
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter()
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

    adapter = LLMAdapter()
    adapter.chat("Just a user message")

    call_args = mock_llm_instance.invoke.call_args[0][0]
    assert len(call_args) == 1
    assert call_args[0].type == "human"


# ---------------------------------------------------------------------------
# 边界条件
# ---------------------------------------------------------------------------


def test_chat_empty_prompt_raises(mocker):
    """空字符串 prompt 抛出 ValueError"""
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})
    adapter = LLMAdapter()

    with pytest.raises(ValueError, match="must not be empty"):
        adapter.chat("")

    with pytest.raises(ValueError, match="must not be empty"):
        adapter.chat("   ")


def test_chat_whitespace_prompt_raises(mocker):
    """纯空白 prompt 抛出 ValueError"""
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})
    adapter = LLMAdapter()

    with pytest.raises(ValueError, match="must not be empty"):
        adapter.chat("\n\t  ")


def test_init_missing_api_key(mocker):
    """DEEPSEEK_API_KEY 缺失时构造函数抛出 ValueError"""
    mocker.patch.dict(os.environ, {}, clear=True)

    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        LLMAdapter()


def test_init_defaults_when_env_vars_missing(mocker):
    """model/base_url 环境变量缺失时使用默认值"""
    mock_llm_class = mocker.patch("src.llm.adapter.ChatOpenAI")
    mock_llm_instance = mocker.MagicMock()
    mock_llm_class.return_value = mock_llm_instance
    mock_llm_instance.invoke.return_value = mocker.MagicMock(content="ok")
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    LLMAdapter()

    mock_llm_class.assert_called_once_with(
        model="deepseek-chat",
        api_key="test-key",
        base_url="https://api.deepseek.com/v1",
        timeout=30,
        max_retries=2,
    )


def test_init_reads_env_vars(mocker):
    """自定义环境变量正确传递给 ChatOpenAI"""
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

    LLMAdapter()

    mock_llm_class.assert_called_once_with(
        model="custom-model",
        api_key="sk-custom",
        base_url="https://custom.api.com/v1",
        timeout=30,
        max_retries=2,
    )


# ---------------------------------------------------------------------------
# 错误路径 — LLM 异常
# ---------------------------------------------------------------------------


def test_chat_api_timeout(mocker):
    """API 超时被捕获并重新抛为 LLMError"""
    from openai import APITimeoutError

    mock_llm_instance = mocker.MagicMock()
    mock_llm_instance.invoke.side_effect = APITimeoutError("Request timed out")
    mocker.patch("src.llm.adapter.ChatOpenAI", return_value=mock_llm_instance)
    mocker.patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"})

    adapter = LLMAdapter()

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

    adapter = LLMAdapter()

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

    adapter = LLMAdapter()

    with pytest.raises(LLMError, match="LLM call failed"):
        adapter.chat("Hello")


# ============================================================================
# 真实 API 调用测试（需要 .env 中配置 DEEPSEEK_API_KEY）
# ============================================================================


@pytest.mark.real
def test_real_chat_simple():
    """真实调用 DeepSeek — 简单对话"""
    from dotenv import load_dotenv

    load_dotenv()

    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY 未设置，跳过真实调用测试")

    adapter = LLMAdapter()
    result = adapter.chat("用一句话介绍 Python 语言")

    # 验证返回了有意义的内容
    assert isinstance(result, str)
    assert len(result) > 0
    assert "Python" in result or "python" in result
    print(f"\n[真实调用] 回复: {result}")


@pytest.mark.real
def test_real_chat_with_system_prompt():
    """真实调用 DeepSeek — 带 System Prompt"""
    from dotenv import load_dotenv

    load_dotenv()

    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY 未设置，跳过真实调用测试")

    adapter = LLMAdapter()
    result = adapter.chat(
        prompt="1 + 1 = ?",
        system_prompt="你是一个数学老师，请用中文回答，只给答案。",
    )

    assert isinstance(result, str)
    assert len(result) > 0
    print(f"\n[真实调用] 数学老师回复: {result}")


@pytest.mark.real
def test_real_chat_long_response():
    """真实调用 DeepSeek — 生成长文本"""
    from dotenv import load_dotenv

    load_dotenv()

    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY 未设置，跳过真实调用测试")

    adapter = LLMAdapter()
    result = adapter.chat("请用中文写一段约100字的自我介绍，你是 LLM Wiki 知识库助手")

    assert isinstance(result, str)
    assert len(result) > 50  # 长文本至少 50 字符
    print(f"\n[真实调用] 回复长度: {len(result)} 字符\n内容: {result}")
