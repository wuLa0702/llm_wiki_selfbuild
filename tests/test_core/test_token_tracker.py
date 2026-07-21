"""
TokenTracker 单元测试
"""
import sqlite3

import pytest

from src.core.pricing import PricingProvider
from src.core.token_tracker import TokenTracker, _format_cost


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_tokens.db")


@pytest.fixture
def pricing(db_path):
    """PricingProvider with seeds (uses tmp DB so种子写入正确)"""
    return PricingProvider(db_path)


@pytest.fixture
def tracker(db_path, pricing):
    return TokenTracker(db_path, pricing=pricing)


def _count_rows(db_path, table="token_usage_log"):
    conn = sqlite3.connect(db_path)
    count = conn.execute(
        f"SELECT COUNT(*) FROM {table}"
    ).fetchone()[0]
    conn.close()
    return count


# ============================================================================
# 记录
# ============================================================================


def test_record_writes_to_db(tracker, db_path):
    """record() 后 SQLite 有记录写入"""
    tracker.record("chat", {
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "model": "deepseek-v4-flash",
        "timestamp": "2026-07-07T10:00:00",
    })
    assert _count_rows(db_path) == 1


def test_record_multiple(tracker, db_path):
    """多次 record 写入多条记录"""
    for i in range(3):
        tracker.record("chat", {
            "input_tokens": 10,
            "output_tokens": 5,
            "total_tokens": 15,
            "model": "deepseek-v4-flash",
            "timestamp": "2026-07-07T10:00:00",
        })
    assert _count_rows(db_path) == 3


def test_record_preserves_fields(tracker, db_path):
    """写入的字段正确完整"""
    tracker.record("chat", {
        "input_tokens": 200,
        "output_tokens": 100,
        "total_tokens": 300,
        "model": "deepseek-v4-flash",
        "timestamp": "2026-07-07T12:00:00",
    })
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM token_usage_log").fetchone()
    conn.close()
    assert row["operation"] == "chat"
    assert row["input_tokens"] == 200
    assert row["output_tokens"] == 100
    assert row["total_tokens"] == 300
    assert row["model"] == "deepseek-v4-flash"


# ============================================================================
# 汇总
# ============================================================================


def test_today_summary_counts(tracker, db_path):
    """today_summary 正确汇总当日数据"""
    from datetime import datetime
    now = datetime.now()
    ts1 = now.replace(hour=10, minute=0, second=0).isoformat()
    ts2 = now.replace(hour=11, minute=0, second=0).isoformat()
    tracker.record("chat", {
        "input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500,
        "model": "deepseek-v4-flash", "timestamp": ts1,
    })
    tracker.record("chat", {
        "input_tokens": 2000, "output_tokens": 1000, "total_tokens": 3000,
        "model": "deepseek-v4-flash", "timestamp": ts2,
    })

    summary = tracker.today_summary()
    assert summary["period"] == "today"
    assert summary["total_tokens"] == 4500
    assert len(summary["by_operation"]) == 1
    assert summary["by_operation"][0]["operation"] == "chat"


def test_today_summary_empty(tracker):
    """无记录时 today_summary 返回零值"""
    summary = tracker.today_summary()
    assert summary["total_tokens"] == 0
    assert summary["by_operation"] == []


def test_today_summary_by_operation(tracker, db_path):
    """不同操作类型分别汇总"""
    from datetime import datetime
    now = datetime.now()
    ts1 = now.replace(hour=10, minute=0, second=0).isoformat()
    ts2 = now.replace(hour=11, minute=0, second=0).isoformat()
    tracker.record("ingest_step1", {
        "input_tokens": 800, "output_tokens": 200, "total_tokens": 1000,
        "model": "deepseek-v4-flash", "timestamp": ts1,
    })
    tracker.record("ingest_step2", {
        "input_tokens": 500, "output_tokens": 150, "total_tokens": 650,
        "model": "deepseek-v4-flash", "timestamp": ts2,
    })

    summary = tracker.today_summary()
    assert summary["total_tokens"] == 1650
    ops = {r["operation"] for r in summary["by_operation"]}
    assert ops == {"ingest_step1", "ingest_step2"}


# ============================================================================
# 费用估算
# ============================================================================


def test_cost_from_seed_price_deepseek_flash(tracker):
    """deepseek-v4-flash 价格从种子 DB 读取，费用计算正确"""
    price = tracker._get_price("deepseek-v4-flash")
    # seed: input=1.00, output=2.00
    cost = tracker._estimate_cost_from_price(1_000_000, 500_000, price)
    assert cost == 2.0  # 1*1 + 0.5*2


def test_cost_from_seed_price_doubao_pro(tracker):
    """doubao-seed-2.1-pro 价格正确"""
    price = tracker._get_price("doubao-seed-2.1-pro")
    # seed: input=6.00, output=30.00
    cost = tracker._estimate_cost_from_price(1_000_000, 100_000, price)
    assert cost == 9.0  # 1*6 + 0.1*30


def test_cost_unknown_model_returns_zero(tracker):
    """未知模型返回 0 价格"""
    price = tracker._get_price("nonexistent-model")
    # 不在种子中 → PricingProvider 返回 default: input=1.00, output=2.00
    # 因为种子里有 default 行
    assert price.get("input_price", 0) > 0


def test_estimate_cost_zero(tracker):
    """零 token 时费用为 0"""
    price = tracker._get_price("deepseek-v4-flash")
    cost = tracker._estimate_cost_from_price(0, 0, price)
    assert cost == 0.0


def test_format_cost_large():
    """¥0.03+ 保留两位小数"""
    assert _format_cost(0.035) == "¥0.04"


def test_format_cost_small():
    """¥0.01 以下保留四位小数"""
    assert _format_cost(0.001) == "¥0.0010"
