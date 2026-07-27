"""
Chat Agent API 路由测试 — POST /v1/agent/chat

策略：
  - Mock build_agent 和 chat_stream 避免真实 LLM 调用
  - 验证 SSE 事件流正确格式
"""
import json
import os

import pytest
from fastapi.testclient import TestClient

from src.main import app


client = TestClient(app)


# ============================================================================
# 正常路径
# ============================================================================


class TestChatRoute:
    """POST /v1/agent/chat 路由测试"""

    @pytest.fixture(autouse=True)
    def _mock_agent(self, mocker):
        """Mock 整个 agent 模块，避免真实 LLM 调用"""
        # Mock build_agent
        self._mock_agent_obj = mocker.MagicMock()
        mocker.patch("src.api.routes.chat.build_agent", return_value=self._mock_agent_obj)

    @pytest.mark.asyncio
    async def test_chat_returns_sse_stream(self):
        """正常请求返回 text/event-stream"""
        # 替换 chat_stream 为可控 async generator
        from src.api.routes.chat import chat_stream as real_chat_stream

        async def mock_stream(agent, messages):
            yield {"type": "token", "content": "你好"}
            yield {"type": "token", "content": "世界"}
            yield {"type": "done", "sources": []}

        original = real_chat_stream
        try:
            import src.api.routes.chat as chat_module
            chat_module.chat_stream = mock_stream

            response = client.post(
                "/v1/agent/chat",
                json={"messages": [{"role": "user", "content": "你好"}]},
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
        finally:
            chat_module.chat_stream = original

    @pytest.mark.asyncio
    async def test_chat_sse_events_parsed(self):
        """SSE 事件能被正确解析"""
        from src.api.routes.chat import chat_stream as real_chat_stream

        async def mock_stream(agent, messages):
            yield {"type": "token", "content": "流式"}
            yield {"type": "tool_start", "tool": "search_wiki", "input": {"query": "test"}}
            yield {"type": "tool_end", "tool": "search_wiki", "output": "结果"}
            yield {"type": "done", "sources": ["entities/test.md"]}

        original = real_chat_stream
        try:
            import src.api.routes.chat as chat_module
            chat_module.chat_stream = mock_stream

            response = client.post(
                "/v1/agent/chat",
                json={"messages": [{"role": "user", "content": "test"}]},
            )
            assert response.status_code == 200

            # 解析 SSE 行
            lines = response.text.strip().split("\n")
            events = []
            for line in lines:
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

            assert len(events) >= 1
            assert events[0]["type"] == "token"
            assert events[0]["content"] == "流式"

            # 验证工具事件
            tool_starts = [e for e in events if e["type"] == "tool_start"]
            assert len(tool_starts) >= 1
            assert tool_starts[0]["tool"] == "search_wiki"

            # 验证 done
            done = [e for e in events if e["type"] == "done"]
            assert len(done) == 1
            assert "entities/test.md" in done[0]["sources"]
        finally:
            chat_module.chat_stream = original

    def test_chat_no_messages(self):
        """空消息列表的错误处理"""
        response = client.post("/v1/agent/chat", json={"messages": []})
        # 应该返回 SSE 流（包含 error 事件），而不是直接 422
        assert response.status_code in (200, 422)

    def test_chat_invalid_json(self):
        """无效请求体返回 422"""
        response = client.post(
            "/v1/agent/chat",
            data="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_chat_sse_stream_headers(self):
        """SSE 响应包含正确的缓存和连接头"""
        from src.api.routes.chat import chat_stream as real_chat_stream

        async def mock_stream(agent, messages):
            yield {"type": "done", "sources": []}

        original = real_chat_stream
        try:
            import src.api.routes.chat as chat_module
            chat_module.chat_stream = mock_stream

            response = client.post(
                "/v1/agent/chat",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
            assert response.status_code == 200
            # SSE 应包含 no-cache 指令（中间件可能追加额外值）
            assert "no-cache" in (response.headers.get("cache-control") or "")
        finally:
            chat_module.chat_stream = original

    def test_chat_with_system_message(self):
        """包含 system 角色的消息"""
        response = client.post(
            "/v1/agent/chat",
            json={
                "messages": [
                    {"role": "system", "content": "请用英文回答"},
                    {"role": "user", "content": "你好"},
                ]
            },
        )
        # System message 应被接受
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_chat_error_in_stream(self):
        """流中发生异常时返回 error 事件"""
        from src.api.routes.chat import chat_stream as real_chat_stream

        async def mock_stream(agent, messages):
            yield {"type": "error", "message": "内部错误"}

        original = real_chat_stream
        try:
            import src.api.routes.chat as chat_module
            chat_module.chat_stream = mock_stream

            response = client.post(
                "/v1/agent/chat",
                json={"messages": [{"role": "user", "content": "test"}]},
            )
            assert response.status_code == 200

            lines = response.text.strip().split("\n")
            events = [json.loads(l[6:]) for l in lines if l.startswith("data: ")]
            error_events = [e for e in events if e["type"] == "error"]
            assert len(error_events) >= 1
        finally:
            chat_module.chat_stream = original


# ============================================================================
# POST /v1/agent/chat/session
# ============================================================================


class TestChatSessionRoute:
    """POST /v1/agent/chat/session 路由测试"""

    @pytest.fixture(autouse=True)
    def _mock_deps(self, mocker):
        """Mock build_agent 避免真实 LLM"""
        self._mock_agent_obj = mocker.MagicMock()
        mocker.patch("src.api.routes.chat.build_agent", return_value=self._mock_agent_obj)

    @pytest.fixture
    def _patch_session(self, mocker):
        """替换 chat_stream_session 为可控 async generator"""
        import src.api.routes.chat as chat_module
        original = chat_module.chat_stream_session

        async def _null_stream(*args, **kwargs):
            yield {"type": "done", "sources": []}
            return

        chat_module.chat_stream_session = _null_stream
        yield
        chat_module.chat_stream_session = original

    @pytest.mark.asyncio
    async def test_session_returns_sse_stream(self, _patch_session):
        """正常请求返回 text/event-stream"""
        import src.api.routes.chat as chat_module

        original = chat_module.chat_stream_session

        async def mock_stream(*args, **kwargs):
            yield {"type": "token", "content": "你好"}
            yield {"type": "done", "sources": []}

        try:
            chat_module.chat_stream_session = mock_stream

            response = client.post(
                "/v1/agent/chat/session",
                json={"content": "你好", "thread_id": "test-thread"},
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
        finally:
            chat_module.chat_stream_session = original

    @pytest.mark.asyncio
    async def test_session_events_fire(self):
        """SSE 事件能被正确解析"""
        import src.api.routes.chat as chat_module

        original = chat_module.chat_stream_session

        async def mock_stream(*args, **kwargs):
            yield {"type": "token", "content": "流式"}
            yield {"type": "done", "sources": []}

        try:
            chat_module.chat_stream_session = mock_stream

            response = client.post(
                "/v1/agent/chat/session",
                json={"content": "test", "thread_id": "t1"},
            )
            assert response.status_code == 200

            lines = response.text.strip().split("\n")
            events = [json.loads(l[6:]) for l in lines if l.startswith("data: ")]
            assert events[0]["type"] == "token"
            assert events[0]["content"] == "流式"
        finally:
            chat_module.chat_stream_session = original

    @pytest.mark.asyncio
    async def test_session_stream_error(self):
        """流中异常返回 error 事件"""
        import src.api.routes.chat as chat_module

        original = chat_module.chat_stream_session

        async def mock_stream(*args, **kwargs):
            yield {"type": "error", "message": "会话异常"}

        try:
            chat_module.chat_stream_session = mock_stream

            response = client.post(
                "/v1/agent/chat/session",
                json={"content": "hi", "thread_id": "err-thread"},
            )
            assert response.status_code == 200

            lines = response.text.strip().split("\n")
            events = [json.loads(l[6:]) for l in lines if l.startswith("data: ")]
            assert events[0]["type"] == "error"
        finally:
            chat_module.chat_stream_session = original

    def test_session_missing_content(self):
        """缺少 content 字段返回 422"""
        response = client.post(
            "/v1/agent/chat/session",
            json={"thread_id": "xxx"},
        )
        assert response.status_code == 422

    def test_session_missing_thread_id(self):
        """缺少 thread_id 字段返回 422"""
        response = client.post(
            "/v1/agent/chat/session",
            json={"content": "hi"},
        )
        assert response.status_code == 422


# ============================================================================
# GET /v1/agent/threads
# ============================================================================


class TestThreadsRoute:
    """GET /v1/agent/threads 路由测试"""

    @pytest.fixture(autouse=True)
    def _mock_deps(self, mocker):
        """Mock 持久化层和 build_agent"""
        mocker.patch("src.api.routes.chat.build_agent", return_value=mocker.MagicMock())

    def test_threads_empty(self, mocker):
        """空数据库返回空列表"""
        mocker.patch("src.api.routes.chat.P.list_threads", return_value=[])

        response = client.get("/v1/agent/threads")
        assert response.status_code == 200
        assert response.json()["threads"] == []

    def test_threads_with_data(self, mocker):
        """有持久化数据时返回列表"""
        mock_data = [
            {"thread_id": "t1", "title": "对话1", "message_count": 5,
             "created_at": 1000.0, "updated_at": 2000.0},
            {"thread_id": "t2", "title": "对话2", "message_count": 3,
             "created_at": 900.0, "updated_at": 1800.0},
        ]
        mocker.patch("src.api.routes.chat.P.list_threads", return_value=mock_data)

        response = client.get("/v1/agent/threads")
        assert response.status_code == 200
        data = response.json()
        assert len(data["threads"]) == 2
        assert data["threads"][0]["thread_id"] == "t1"
        assert data["threads"][1]["thread_id"] == "t2"

    def test_threads_with_limit_query(self, mocker):
        """limit 查询参数被传递"""
        mock_list = mocker.patch("src.api.routes.chat.P.list_threads", return_value=[])

        response = client.get("/v1/agent/threads?limit=5")
        assert response.status_code == 200
        assert mock_list.call_args[1]["limit"] == 5

    def test_threads_with_offset_query(self, mocker):
        """offset 查询参数被传递"""
        mock_list = mocker.patch("src.api.routes.chat.P.list_threads", return_value=[])

        response = client.get("/v1/agent/threads?offset=10")
        assert response.status_code == 200
        assert mock_list.call_args[1]["offset"] == 10
