"""
Auth API 集成测试 — Phase 4 Step 6
"""
from fastapi.testclient import TestClient

from src.core.auth import _active_tokens

# 用 test 模式导入 main
import sys
sys.path.insert(0, ".")

from src.main import app

client = TestClient(app)


def setup_function():
    """每个测试前清空 token 和密码"""
    _active_tokens.clear()
    # 清除可能残留的密码
    from src.main import _get_pm
    pm = _get_pm()
    if pm.is_protected():
        pm.clear()


# ============================================================================
# 设置密码
# ============================================================================


def test_set_password():
    """POST /v1/auth/password 设置密码"""
    r = client.post("/v1/auth/password", json={"password": "test-1234"})
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_set_password_too_short():
    """密码太短返回 400"""
    r = client.post("/v1/auth/password", json={"password": "ab"})
    assert r.status_code == 400


def test_set_password_missing():
    """缺少 password 字段返回 400"""
    r = client.post("/v1/auth/password", json={})
    assert r.status_code == 400


# ============================================================================
# 验证密码
# ============================================================================


def test_verify_correct():
    """正确密码返回 token"""
    client.post("/v1/auth/password", json={"password": "test-1234"})
    r = client.post("/v1/auth/verify", json={"password": "test-1234"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "token" in data
    assert len(data["token"]) == 64


def test_verify_wrong():
    """错误密码返回 403"""
    client.post("/v1/auth/password", json={"password": "test-1234"})
    r = client.post("/v1/auth/verify", json={"password": "wrong"})
    assert r.status_code == 403


# ============================================================================
# 清除密码
# ============================================================================


def test_clear_password():
    """POST /v1/auth/clear 清除密码"""
    client.post("/v1/auth/password", json={"password": "test-1234"})
    r = client.post("/v1/auth/clear")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ============================================================================
# 状态查询
# ============================================================================


def test_auth_status_protected():
    """设置密码后 /v1/auth/status 返回 protected=True"""
    client.post("/v1/auth/password", json={"password": "test-1234"})
    r = client.get("/v1/auth/status")
    assert r.json()["protected"] is True


def test_auth_status_unprotected():
    """未设置密码时 /v1/auth/status 返回 protected=False"""
    r = client.get("/v1/auth/status")
    assert r.json()["protected"] is False
