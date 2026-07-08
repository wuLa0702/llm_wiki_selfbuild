"""
PasswordManager + Auth API 单元测试 — Phase 4 Step 6
"""
import bcrypt
import pytest

from src.core.auth import PasswordManager, _active_tokens


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_repo(mocker):
    """模拟 WikiRepository，wiki_settings 存在内存 dict 中"""
    repo = mocker.MagicMock()
    _settings: dict[str, str] = {}

    def _get(key):
        return _settings.get(key)

    def _set(key, value):
        _settings[key] = value

    def _delete(key):
        _settings.pop(key, None)

    repo.get_setting.side_effect = _get
    repo.set_setting.side_effect = _set
    repo.delete_setting.side_effect = _delete
    return repo


@pytest.fixture
def pm(mock_repo):
    _active_tokens.clear()
    return PasswordManager(mock_repo)


# ============================================================================
# set_password
# ============================================================================


def test_set_password(pm):
    """设置密码后 is_protected 返回 True"""
    pm.set_password("my-secret-1234")
    assert pm.is_protected() is True


def test_set_password_short_rejected(pm):
    """过短的密码拒绝设置"""
    with pytest.raises(ValueError, match="至少 4 位"):
        pm.set_password("ab")


def test_set_password_empty_rejected(pm):
    """空密码拒绝设置"""
    with pytest.raises(ValueError, match="至少 4 位"):
        pm.set_password("")


def test_set_password_stores_hash(pm, mock_repo):
    """密码存储的是 bcrypt 哈希，不是明文"""
    pm.set_password("my-secret")
    stored = mock_repo.get_setting("access_password")
    assert stored is not None
    assert stored != "my-secret"
    # 是有效的 bcrypt 哈希
    assert bcrypt.checkpw("my-secret".encode("utf-8"), stored.encode("utf-8"))


# ============================================================================
# verify
# ============================================================================


def test_verify_correct(pm):
    """正确密码验证通过"""
    pm.set_password("my-secret")
    assert pm.verify("my-secret") is True


def test_verify_wrong(pm):
    """错误密码验证不通过"""
    pm.set_password("my-secret")
    assert pm.verify("wrong-password") is False


def test_verify_no_password(pm):
    """未设置密码时验证失败"""
    assert pm.verify("anything") is False


# ============================================================================
# clear
# ============================================================================


def test_clear_password(pm):
    """清除密码后 is_protected 返回 False"""
    pm.set_password("my-secret")
    assert pm.is_protected() is True
    pm.clear()
    assert pm.is_protected() is False


def test_clear_clears_tokens(pm):
    """清除密码后所有 token 失效"""
    pm.set_password("my-secret")
    token = pm.create_token()
    assert pm.validate_token(token) is True
    pm.clear()
    assert pm.validate_token(token) is False


# ============================================================================
# Token
# ============================================================================


def test_create_token(pm):
    """create_token 返回有效的 token 字符串"""
    pm.set_password("my-secret")
    token = pm.create_token()
    assert len(token) == 64  # 32 bytes hex
    assert pm.validate_token(token) is True


def test_validate_token_invalid(pm):
    """无效 token 验证失败"""
    pm.set_password("my-secret")
    assert pm.validate_token("invalid-token") is False


def test_revoke_token(pm):
    """revoke_token 使 token 失效"""
    pm.set_password("my-secret")
    token = pm.create_token()
    assert pm.validate_token(token) is True
    pm.revoke_token(token)
    assert pm.validate_token(token) is False


def test_password_change_clears_tokens(pm):
    """修改密码后所有 token 失效"""
    pm.set_password("my-secret")
    token = pm.create_token()
    assert pm.validate_token(token) is True
    # 修改密码
    pm.set_password("new-secret-5678")
    assert pm.validate_token(token) is False


# ============================================================================
# token_info
# ============================================================================


def test_token_info(pm):
    """token_info 返回正确统计"""
    pm.set_password("my-secret")
    for _ in range(3):
        pm.create_token()
    info = pm.token_info()
    assert info["active_tokens"] == 3
    assert info["ttl_seconds"] == 86400
