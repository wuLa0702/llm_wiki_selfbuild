"""
密码保护模块 — Phase 4 Step 6

基于 bcrypt 哈希存储密码，验证后生成短期 token 维持登录状态。

哲学：不拦截内容生成，只限制访问。
"""
import secrets
import time
from datetime import datetime

import bcrypt

from src.core.logging_config import get_logger

logger = get_logger("auth")

# Token 有效期（秒）
TOKEN_TTL = 86400  # 24 小时

# 内存 token 存储 {token: created_at}
_active_tokens: dict[str, float] = {}

SETTINGS_KEY = "access_password"


class PasswordManager:
    """密码管理 — 用于保护 restricted 页面"""

    def __init__(self, repo) -> None:
        """
        Args:
            repo: WikiRepository 实例（需支持 get_setting / set_setting / delete_setting）
        """
        self.repo = repo

    # ------------------------------------------------------------------
    # 密码管理
    # ------------------------------------------------------------------

    def set_password(self, password: str) -> None:
        """
        设置/更新 Wiki 访问密码

        Args:
            password: 明文密码（至少 4 位）
        """
        if not password or len(password) < 4:
            raise ValueError("密码至少 4 位")
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        self.repo.set_setting(SETTINGS_KEY, hashed.decode("utf-8"))
        # 清除所有现有 token（密码变更后需要重新登录）
        _active_tokens.clear()
        logger.info("密码已设置")

    def verify(self, password: str) -> bool:
        """
        验证密码

        Args:
            password: 待验证的明文密码

        Returns:
            True 验证通过
        """
        hashed = self.get_hashed_password()
        if hashed is None:
            return False
        try:
            return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
        except Exception as exc:
            logger.error("密码验证异常 | %s", exc)
            return False

    def is_protected(self) -> bool:
        """是否已设置密码"""
        return self.get_hashed_password() is not None

    def clear(self) -> None:
        """清除密码（恢复公开访问）"""
        self.repo.delete_setting(SETTINGS_KEY)
        _active_tokens.clear()
        logger.info("密码已清除")

    def get_hashed_password(self) -> str | None:
        """获取已存储的密码哈希"""
        return self.repo.get_setting(SETTINGS_KEY)

    # ------------------------------------------------------------------
    # Token 管理
    # ------------------------------------------------------------------

    def create_token(self) -> str:
        """
        验证密码后创建访问 token

        Returns:
            token 字符串
        """
        token = secrets.token_hex(32)
        _active_tokens[token] = time.time()
        # 清理过期 token
        self._cleanup_tokens()
        return token

    def validate_token(self, token: str) -> bool:
        """
        验证 token 是否有效

        Args:
            token: 待验证的 token

        Returns:
            True 有效
        """
        created = _active_tokens.get(token)
        if created is None:
            return False
        if time.time() - created > TOKEN_TTL:
            del _active_tokens[token]
            return False
        return True

    def revoke_token(self, token: str) -> None:
        """主动失效指定 token"""
        _active_tokens.pop(token, None)

    @staticmethod
    def _cleanup_tokens() -> None:
        """清理过期 token"""
        now = time.time()
        expired = [t for t, c in _active_tokens.items() if now - c > TOKEN_TTL]
        for t in expired:
            del _active_tokens[t]

    def token_info(self) -> dict:
        """
        返回当前 token 状态统计

        Returns:
            {"active_tokens": 3, "ttl_seconds": 86400}
        """
        self._cleanup_tokens()
        return {
            "active_tokens": len(_active_tokens),
            "ttl_seconds": TOKEN_TTL,
        }


# ====================================================================
# 密码保护状态检查（供中间件使用）
# ====================================================================

# 缓存 is_protected 状态，减少 SQLite 查询
_protected_cache: dict = {"value": False, "expires_at": 0}
_PROTECTED_CACHE_TTL = 60  # 60 秒


def is_wiki_protected(repo) -> bool:
    """检查 Wiki 是否设置了密码（带 60s 缓存）"""
    global _protected_cache
    now = time.time()
    if now < _protected_cache["expires_at"]:
        return _protected_cache["value"]

    pm = PasswordManager(repo)
    protected = pm.is_protected()
    _protected_cache = {"value": protected, "expires_at": now + _PROTECTED_CACHE_TTL}
    return protected
