"""
PricingProvider 单元测试
"""
import sqlite3
from datetime import datetime, timedelta

import pytest

from src.core.pricing import PricingProvider, SEED_PRICES


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_pricing.db")


@pytest.fixture
def provider(db_path):
    return PricingProvider(db_path)


# ============================================================================
# 种子数据
# ============================================================================


def test_seed_data_loaded(provider, db_path):
    """种子数据首次写入 DB"""
    conn = sqlite3.connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM model_pricing").fetchone()[0]
    conn.close()
    assert count >= len(SEED_PRICES) - 1  # default fallback included


def test_seed_contains_deepseek_flash(provider):
    """deepseek-v4-flash 价格正确"""
    price = provider.get_price("deepseek-v4-flash")
    assert price is not None
    assert price["input_price"] == 1.00
    assert price["output_price"] == 2.00
    assert price["provider"] == "deepseek"


def test_seed_contains_deepseek_pro(provider):
    """deepseek-v4-pro 价格正确"""
    price = provider.get_price("deepseek-v4-pro")
    assert price is not None
    assert price["input_price"] == 3.00
    assert price["output_price"] == 6.00
    assert price["cache_hit_price"] == 0.025


def test_seed_contains_doubao_pro(provider):
    """doubao-seed-2.1-pro 价格正确"""
    price = provider.get_price("doubao-seed-2.1-pro")
    assert price is not None
    assert price["input_price"] == 6.00
    assert price["output_price"] == 30.00
    assert price["provider"] == "doubao"


def test_default_fallback_exists(provider):
    """default 行存在"""
    price = provider.get_price("default")
    assert price is not None


def test_seed_not_overwritten_on_reinit(provider, db_path):
    """重复初始化不覆盖已有种子数据"""
    count1 = sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) FROM model_pricing"
    ).fetchone()[0]
    PricingProvider(db_path)
    count2 = sqlite3.connect(db_path).execute(
        "SELECT COUNT(*) FROM model_pricing"
    ).fetchone()[0]
    assert count1 == count2


# ============================================================================
# 查询
# ============================================================================


def test_get_price_returns_cached(provider):
    """种子模型返回完整价格信息"""
    price = provider.get_price("deepseek-v4-flash")
    assert price is not None
    assert "model" in price
    assert "input_price" in price
    assert "output_price" in price
    assert "is_stale" in price


def test_get_price_unknown_model_fallsback_to_default(provider):
    """未知模型 fallback 到 default"""
    price = provider.get_price("totally-unknown-model-v99")
    assert price is not None
    assert price["input_price"] == 1.00  # default


def test_get_price_source_url_and_fetched_at(provider):
    """返回的结果包含 source_url 和 fetched_at"""
    price = provider.get_price("deepseek-v4-flash")
    assert price["source_url"] != ""
    assert price["fetched_at"] != ""


# ============================================================================
# 过期检测
# ============================================================================


def test_is_stale_false_for_recently_fetched(provider):
    """刚写入的价格不过期"""
    # 种子数据是刚写入的
    price = provider.get_price("deepseek-v4-flash")
    assert price["is_stale"] is False


def test_is_stale_24h_old(provider, db_path):
    """24h 前的价格标记为过期"""
    # 手动插入一条旧数据
    old_time = (datetime.now() - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT OR REPLACE INTO model_pricing
            (model, provider, input_price, output_price, cache_hit_price,
             currency, source_url, fetched_at)
        VALUES (?, 'deepseek', 1.0, 2.0, 0.0, 'CNY', '', ?)
        """,
        ("stale-model", old_time),
    )
    conn.commit()
    conn.close()

    price = provider.get_price("stale-model")
    assert price["is_stale"] is True


# ============================================================================
# 页面解析器
# ============================================================================


def test_extract_deepseek_pricing():
    """DeepSeek HTML 中的横向价格表能被解析"""
    sample_html = """\
| 模型 | deepseek-v4-flash(1) | deepseek-v4-pro |
| 价格 | 百万tokens输入（缓存命中） | 0.02元 | 0.025元 |
|  | 百万tokens输入（缓存未命中） | 1元 | 3元 |
|  | 百万tokens输出 | 2元 | 6元 |
"""
    result = PricingProvider._extract_pricing_table(sample_html, "https://api-docs.deepseek.com/zh-cn/quick_start/pricing")
    models = {r["model"] for r in result}
    assert "deepseek-v4-flash" in models
    assert "deepseek-v4-pro" in models


def test_extract_volcengine_pricing():
    """火山引擎 HTML 中的纵向价格表能被解析"""
    sample_html = """\
| 模型名称 | 条件 | 输入(非音频)元/百万token | 缓存命中(非音频)元/百万token | 输出元/百万token |
| --- | --- | --- | --- | --- |
| doubao-seed-2.1-pro | 输入长度 [0, 256] | 6.00 | 1.20 | 30.00 |
| doubao-seed-2.1-turbo | 输入长度 [0, 256] | 3.00 | 0.60 | 15.00 |
| doubao-seed-2.0-lite | 输入长度 [0, 32] | 0.60 | 0.12 | 3.60 |
"""
    result = PricingProvider._extract_pricing_table(
        "在线推理（常规）\n" + sample_html + "\n在线推理（低延迟）",
        "https://www.volcengine.com/docs/82379/1544106",
    )
    models = {r["model"] for r in result}
    assert "doubao-seed-2.1-pro" in models
    assert "doubao-seed-2.1-turbo" in models
    assert len(result) == 3


def test_extract_volcengine_returns_correct_prices():
    """火山引擎解析返回正确的价格"""
    sample_html = """\
在线推理（常规）
| doubao-seed-2.1-pro | 条件 | 6.00 | 1.20 | 30.00 |
在线推理（低延迟）
"""
    result = PricingProvider._extract_pricing_table(sample_html, "https://www.volcengine.com/docs/82379/1544106")
    assert len(result) == 1
    assert result[0]["input_price"] == 6.00
    assert result[0]["output_price"] == 30.00
    assert result[0]["cache_hit"] == 1.20


# ============================================================================
# upsert — 写入新价格
# ============================================================================


def test_upsert_price(provider, db_path):
    """_upsert_price 写入新模型价格"""
    provider._upsert_price(
        model="test-model",
        provider="deepseek",
        input_price=5.0,
        output_price=10.0,
        cache_hit=0.5,
        source_url="https://example.com",
    )
    price = provider.get_price("test-model")
    assert price["input_price"] == 5.0
    assert price["output_price"] == 10.0
