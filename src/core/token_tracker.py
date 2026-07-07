"""
Token 消耗追踪器 — 内存汇聚 + SQLite 持久化

提供记录、当日/周汇总、费用估算功能。
费用从 PricingProvider 动态查询，不再硬编码。
"""
import sqlite3
from datetime import datetime, timedelta

from src.core.logging_config import get_logger
from src.core.pricing import PricingProvider

logger = get_logger("token_tracker")


def _format_cost(cost: float) -> str:
    """将费用格式化为可读字符串（如 ¥0.03）"""
    if cost < 0.01:
        return f"¥{cost:.4f}"
    return f"¥{cost:.2f}"


class TokenTracker:
    """Token 消耗追踪器 — 内存汇聚 + SQLite 持久化"""

    def __init__(
        self, db_path: str = "wiki.db", pricing: PricingProvider | None = None
    ) -> None:
        """
        Args:
            db_path: SQLite 数据库路径
            pricing: 价格查询器，不传则使用默认 PricingProvider(db_path)
        """
        self.db_path = db_path
        self.pricing = pricing or PricingProvider(db_path)
        self._ensure_table()

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        """确保 token_usage_log 表存在"""
        conn = self._get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                operation TEXT NOT NULL,
                input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL,
                total_tokens INTEGER NOT NULL,
                model TEXT NOT NULL,
                timestamp TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        conn.close()

    def _get_price(self, model: str) -> dict:
        """查询模型价格，不存在时返回零价"""
        price = self.pricing.get_price(model)
        if price is None:
            return {"input_price": 0.0, "output_price": 0.0, "source_url": ""}
        return price

    @staticmethod
    def _estimate_cost_from_price(
        input_tokens: int, output_tokens: int, price: dict
    ) -> float:
        """根据价格字典计算费用"""
        input_cost = input_tokens / 1_000_000 * price.get("input_price", 0.0)
        output_cost = output_tokens / 1_000_000 * price.get("output_price", 0.0)
        return round(input_cost + output_cost, 6)

    # ------------------------------------------------------------------
    # 记录
    # ------------------------------------------------------------------

    def record(self, operation: str, usage: dict) -> None:
        """
        记录一次 LLM 调用的 token 消耗

        Args:
            operation: 操作类型（chat / chat_template / chat_structured / etc.）
            usage: 来自 LLMAdapter.last_usage 的字典，包含：
                   - input_tokens, output_tokens, total_tokens, model, timestamp
        """
        conn = self._get_connection()
        conn.execute(
            """
            INSERT INTO token_usage_log
                (operation, input_tokens, output_tokens, total_tokens, model, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                operation,
                usage.get("input_tokens", 0),
                usage.get("output_tokens", 0),
                usage.get("total_tokens", 0),
                usage.get("model", "unknown"),
                usage.get("timestamp", datetime.now().isoformat()),
            ),
        )
        conn.commit()
        conn.close()

        logger.debug(
            "token recorded | op=%s total=%d model=%s",
            operation,
            usage.get("total_tokens", 0),
            usage.get("model", "unknown"),
        )

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------

    def _range_summary(self, since: str, label: str) -> dict:
        """
        按时间范围查询汇总

        Args:
            since: ISO 时间下限（如 '2026-07-07 00:00:00'）
            label: 时间段标签（如 'today' / 'week'）

        Returns:
            {
                "period": "today",
                "total_tokens": 15000,
                "total_cost_estimate": "¥0.03",
                "by_operation": [{"operation": "chat", "tokens": 5000, ...}, ...]
            }
        """
        conn = self._get_connection()

        total_row = conn.execute(
            """
            SELECT
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(input_tokens), 0) as total_input,
                COALESCE(SUM(output_tokens), 0) as total_output
            FROM token_usage_log
            WHERE timestamp >= ?
            """,
            (since,),
        ).fetchone()

        op_rows = conn.execute(
            """
            SELECT
                operation,
                COALESCE(SUM(total_tokens), 0) as tokens,
                COALESCE(SUM(input_tokens), 0) as input_tokens,
                COALESCE(SUM(output_tokens), 0) as output_tokens
            FROM token_usage_log
            WHERE timestamp >= ?
            GROUP BY operation
            ORDER BY tokens DESC
            """,
            (since,),
        ).fetchall()

        # 用最近使用的模型价格来计算费用
        model_row = conn.execute(
            """
            SELECT model FROM token_usage_log
            WHERE timestamp >= ?
            ORDER BY timestamp DESC LIMIT 1
            """,
            (since,),
        ).fetchone()

        conn.close()

        model = model_row["model"] if model_row else "default"
        price = self._get_price(model)
        total_input = total_row["total_input"]
        total_output = total_row["total_output"]
        total_cost = self._estimate_cost_from_price(total_input, total_output, price)

        by_operation = []
        for r in op_rows:
            op_cost = self._estimate_cost_from_price(
                r["input_tokens"], r["output_tokens"], price
            )
            by_operation.append({
                "operation": r["operation"],
                "tokens": r["tokens"],
                "cost_estimate": _format_cost(op_cost),
            })

        return {
            "period": label,
            "total_tokens": total_row["total_tokens"],
            "total_cost_estimate": _format_cost(total_cost),
            "by_operation": by_operation,
        }

    def today_summary(self) -> dict:
        """返回当日汇总"""
        today_start = datetime.now().strftime("%Y-%m-%d 00:00:00")
        return self._range_summary(today_start, "today")

    def weekly_summary(self) -> dict:
        """返回近 7 天汇总"""
        week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        return self._range_summary(week_ago, "week")
