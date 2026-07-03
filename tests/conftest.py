"""
pytest 配置 — 测试夹具
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI 测试客户端"""
    from src.main import app
    return TestClient(app)
