"""
pytest 配置 — 测试夹具
"""
import pytest
from fastapi.testclient import TestClient


def pytest_configure(config):
    """注册自定义 markers"""
    config.addinivalue_line(
        "markers", "real: 真实 API 调用测试（需要 .env 中配置 API Key）"
    )
    config.addinivalue_line(
        "markers", "asyncio: async test (pytest-asyncio)"
    )


@pytest.fixture
def client():
    """FastAPI 测试客户端"""
    from src.main import app
    return TestClient(app)
