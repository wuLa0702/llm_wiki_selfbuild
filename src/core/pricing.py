"""
模型价格管理器 — SQLite 缓存 + Web 抓取

价格数据来源：
- DeepSeek: https://api-docs.deepseek.com/zh-cn/quick_start/pricing
- 火山引擎: https://www.volcengine.com/docs/82379/1544106
"""
import sqlite3
from datetime import datetime, timedelta

from src.core.logging_config import get_logger

logger = get_logger("pricing")

# ---------------------------------------------------------------------------
# 种子价格数据（首次运行时写入 DB）
# ---------------------------------------------------------------------------
# (model, provider, input_price, output_price, cache_hit_price, source_url)
SEED_PRICES: list[tuple[str, str, float, float, float, str]] = [
    # DeepSeek 官方 — https://api-docs.deepseek.com/zh-cn/quick_start/pricing
    ("deepseek-v4-flash", "deepseek",    1.00, 2.00, 0.02,
     "https://api-docs.deepseek.com/zh-cn/quick_start/pricing"),
    ("deepseek-v4-pro",   "deepseek",    3.00, 6.00, 0.025,
     "https://api-docs.deepseek.com/zh-cn/quick_start/pricing"),
    ("deepseek-chat",     "deepseek",    1.00, 2.00, 0.02,
     "https://api-docs.deepseek.com/zh-cn/quick_start/pricing"),  # 兼容旧名
    ("deepseek-reasoner", "deepseek",    1.00, 2.00, 0.02,
     "https://api-docs.deepseek.com/zh-cn/quick_start/pricing"),  # 兼容旧名
    # 豆包 — https://www.volcengine.com/docs/82379/1544106（在线推理常规）
    ("doubao-seed-2.1-pro",   "doubao",  6.00, 30.00, 1.20,
     "https://www.volcengine.com/docs/82379/1544106"),
    ("doubao-seed-2.1-turbo", "doubao",  3.00, 15.00, 0.60,
     "https://www.volcengine.com/docs/82379/1544106"),
    ("doubao-seed-2.0-pro",   "doubao",  3.20, 16.00, 0.64,
     "https://www.volcengine.com/docs/82379/1544106"),
    ("doubao-seed-2.0-lite",  "doubao",  0.60, 3.60, 0.12,
     "https://www.volcengine.com/docs/82379/1544106"),
    ("doubao-seed-2.0-mini",  "doubao",  0.20, 2.00, 0.04,
     "https://www.volcengine.com/docs/82379/1544106"),
    # default fallback（不在 DB 中的模型）
    ("default",               "unknown", 1.00, 2.00, 0.0, ""),
]


# ---------------------------------------------------------------------------
# 抓取源定义
# ---------------------------------------------------------------------------

class PricingSource:
    """价格来源网站及其对应的抓取配置"""
    def __init__(self, name: str, url: str, parser_method: str) -> None:
        self.name = name
        self.url = url
        self.parser_method = parser_method  # PricingProvider 上对应的静态方法名


SOURCES = [
    PricingSource("DeepSeek",
                  "https://api-docs.deepseek.com/zh-cn/quick_start/pricing",
                  "_parse_deepseek_page"),
    PricingSource("火山引擎",
                  "https://www.volcengine.com/docs/82379/1544106",
                  "_parse_volcengine_page"),
]

# 缓存过期时间
CACHE_TTL = timedelta(hours=24)


class PricingProvider:
    """模型价格查询器 — DB 缓存 + Web 抓取"""

    def __init__(self, db_path: str = "wiki.db") -> None:
        self.db_path = db_path
        self._ensure_table()
        self._ensure_seeds()

    # ------------------------------------------------------------------
    # 内部 — DB 连接
    # ------------------------------------------------------------------

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_table(self) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS model_pricing (
                model TEXT PRIMARY KEY,
                provider TEXT NOT NULL DEFAULT 'unknown',
                input_price REAL NOT NULL,
                output_price REAL NOT NULL,
                cache_hit_price REAL DEFAULT 0,
                currency TEXT DEFAULT 'CNY',
                source_url TEXT,
                fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        conn.close()

    def _ensure_seeds(self) -> None:
        """首次运行时写入种子价格数据"""
        conn = self._get_connection()
        existing = conn.execute(
            "SELECT COUNT(*) as n FROM model_pricing"
        ).fetchone()["n"]
        if existing > 0:
            conn.close()
            return
        for row in SEED_PRICES:
            conn.execute(
                """
                INSERT OR IGNORE INTO model_pricing
                    (model, provider, input_price, output_price,
                     cache_hit_price, source_url, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                row,
            )
        conn.commit()
        conn.close()
        logger.info("种子价格数据已写入 | count=%d", len(SEED_PRICES))

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_price(self, model: str) -> dict | None:
        """
        从 DB 查询模型价格

        如果缓存超过 24h，尝试后台刷新（不阻塞查询）。
        返回 None 表示模型无价格数据。

        Returns:
            {"model": ..., "input_price": ..., "output_price": ...,
             "cache_hit_price": ..., "source_url": ..., "is_stale": bool}
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM model_pricing WHERE model = ?",
            (model,),
        ).fetchone()
        conn.close()

        if row is None:
            # 新模型 → 尝试抓取
            logger.info("新模型无定价，尝试抓取 | model=%s", model)
            self._try_fetch_for_model(model)
            conn = self._get_connection()
            row = conn.execute(
                "SELECT * FROM model_pricing WHERE model = ?",
                (model,),
            ).fetchone()
            conn.close()

        if row is None:
            # 抓取失败，尝试用 default
            conn = self._get_connection()
            row = conn.execute(
                "SELECT * FROM model_pricing WHERE model = 'default'"
            ).fetchone()
            conn.close()

        if row is None:
            return None

        result = dict(row)
        result["is_stale"] = self._is_stale(result.get("fetched_at", ""))
        return result

    def _is_stale(self, fetched_at: str) -> bool:
        """判断价格是否过期"""
        if not fetched_at:
            return True
        try:
            fetched = datetime.strptime(fetched_at[:19], "%Y-%m-%d %H:%M:%S")
            return datetime.now() - fetched > CACHE_TTL
        except (ValueError, IndexError):
            return True

    # ------------------------------------------------------------------
    # 刷新
    # ------------------------------------------------------------------

    def _upsert_price(self, model: str, provider: str,
                      input_price: float, output_price: float,
                      cache_hit: float, source_url: str) -> None:
        conn = self._get_connection()
        conn.execute(
            """
            INSERT OR REPLACE INTO model_pricing
                (model, provider, input_price, output_price,
                 cache_hit_price, source_url, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (model, provider, input_price, output_price,
             cache_hit, source_url),
        )
        conn.commit()
        conn.close()

    def _try_fetch_for_model(self, model: str) -> bool:
        """
        尝试抓取所有来源，如果找到匹配的模型价格则写入 DB

        Returns:
            True if 找到并写入了，False 否则
        """
        all_prices = self._fetch_all_sources()
        for p in all_prices:
            if p["model"] == model:
                self._upsert_price(**p)
                logger.info("抓取到新模型定价 | model=%s", model)
                return True
        # 没找到精确匹配时，看看有没有 provider 级别的已知价格
        # 这里只记录，不做自动猜测
        logger.warning("无法抓取模型定价 | model=%s", model)
        return False

    def _fetch_all_sources(self) -> list[dict]:
        """遍历所有 PriceSource 抓取价格"""
        all_prices: list[dict] = []
        for source in SOURCES:
            try:
                parser = getattr(self, source.parser_method, None)
                if parser:
                    prices = parser(source.url)
                    all_prices.extend(prices)
                    logger.info("价格抓取成功 | source=%s count=%d",
                                source.name, len(prices))
            except Exception as exc:
                logger.warning("价格抓取失败 | source=%s error=%s",
                               source.name, exc)
        return all_prices

    def refresh_top_active(self, top_n: int = 10) -> int:
        """
        刷新 token_usage_log 中最活跃的 N 个模型的价格

        Returns:
            成功刷新的模型数量
        """
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT model, SUM(total_tokens) as usage_count
            FROM token_usage_log
            WHERE timestamp >= datetime('now', '-7 days')
            GROUP BY model
            ORDER BY usage_count DESC
            LIMIT ?
            """,
            (top_n,),
        ).fetchall()
        conn.close()

        active_models = [r["model"] for r in rows if r["model"] != "unknown"]
        if not active_models:
            return 0

        all_prices = self._fetch_all_sources()
        updated = 0
        for model in active_models:
            for p in all_prices:
                if p["model"] == model:
                    self._upsert_price(**p)
                    updated += 1
                    break
            # 不在抓取结果中的模型可能是自建精调模型 → 跳过
        return updated

    # ==================================================================
    # 页面解析器
    # ==================================================================

    @staticmethod
    def _parse_deepseek_page(url: str) -> list[dict]:
        """
        抓取并解析 DeepSeek 中文定价页

        返回: [{model, provider, input_price, output_price, cache_hit, source_url}]
        """
        # 尝试 Firecrawl 抓取
        prices = PricingProvider._try_firecrawl_fetch(
            url,
            "从官方定价页面提取所有模型的价格数据（百万tokens，元）",
        )
        if prices:
            return prices

        # Firecrawl 失败时返回种子数据（至少有一份）
        logger.warning("DeepSeek 页面抓取失败，使用上次缓存")
        return []

    @staticmethod
    def _parse_volcengine_page(url: str) -> list[dict]:
        """
        抓取并解析火山引擎定价页

        返回: [{model, provider, input_price, output_price, cache_hit, source_url}]
        """
        prices = PricingProvider._try_firecrawl_fetch(
            url,
            "从大语言模型在线推理常规价格表中提取所有模型名称和价格（元/百万token），"
            "包括模型名称、输入价格、缓存命中价格、输出价格。只提取大语言模型在线推理常规的价格表。",
        )
        if prices:
            return prices

        logger.warning("火山引擎页面抓取失败，使用上次缓存")
        return []

    @staticmethod
    def _try_firecrawl_fetch(url: str, prompt: str) -> list[dict]:
        """
        尝试用 Firecrawl 的 JSON extraction 抓取定价数据

        Returns:
            解析后的价格列表，或空列表表示失败
        """
        # 尝试在运行时导入 firecrawl MCP 工具
        # 由于运行环境限制，这里使用标准 HTTP 请求作为备用方案
        import json
        try:
            from urllib.request import urlopen, Request

            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/120.0.0.0 Safari/537.36",
            })
            with urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8")
        except Exception as exc:
            logger.warning("HTTP 抓取失败 | url=%s error=%s", url, exc)
            return []

        # 解析 HTML 提取价格表
        return PricingProvider._extract_pricing_table(html, url)

    @staticmethod
    def _extract_pricing_table(html: str, source_url: str) -> list[dict]:
        """
        从 HTML 中提取 Markdown 式价格表

        DeepSeek 中文页：横向表格，列=模型
          | 模型 | deepseek-v4-flash(1) | deepseek-v4-pro |
          | 百万tokens输入（缓存未命中） | 1元 | 3元 |
          | 百万tokens输出 | 2元 | 6元 |

        火山引擎：纵向表格，行=模型
          | doubao-seed-2.1-pro | ... | 6.00 | ... | 30.00 |
        """
        import re

        results: list[dict] = []

        # 通用步骤：提取所有 pipe 表格行
        lines = html.split("\n")
        pipe_rows = [l.strip() for l in lines if l.strip().startswith("|")]

        # ---------------------------------------------------------------
        # DeepSeek 横向表格解析
        # 找到包含模型的表头行，然后按列匹配价格
        # ---------------------------------------------------------------
        if "deepseek" in source_url:
            # 找模型名行：| 模型 | deepseek-v4-flash(1) | deepseek-v4-pro |
            model_row = None
            for row in pipe_rows:
                cells = [c.strip() for c in row.split("|") if c.strip()]
                if len(cells) >= 3 and "deepseek" in row:
                    model_row = cells
                    break

            if model_row:
                # cells[1:] = 模型名列表（跳过第一列"模型"）
                models = []
                for c in model_row[1:]:
                    m = re.sub(r"\([^)]*\)", "", c).strip()  # 去掉 (1) 后缀
                    if "deepseek" in m:
                        models.append(m)

                if models:
                    # 找价格行
                    for row in pipe_rows:
                        cells = [c.strip() for c in row.split("|") if c.strip()]
                        if len(cells) < len(models) + 1:
                            continue
                        # 提取所有数字+元 的值
                        prices = []
                        for c in cells[1:1 + len(models)]:
                            pm = re.match(r"(\d+(?:\.\d+)?)元", c.strip())
                            if pm:
                                prices.append(float(pm.group(1)))
                            else:
                                prices.append(None)

                        # 根据行文本判断价格类型
                        row_text = " ".join(cells).lower()
                        if "缓存命中" in row_text and "缓存未命中" not in row_text:
                            for i, p in enumerate(prices):
                                if p is not None:
                                    # 找到已有模型，更新 cache_hit
                                    for r in results:
                                        if r["model"] == models[i]:
                                            r["cache_hit"] = p
                        elif "缓存未命中" in row_text and "输出" not in row_text:
                            for i, p in enumerate(prices):
                                if p is not None:
                                    results.append({
                                        "model": models[i],
                                        "provider": "deepseek",
                                        "input_price": p,
                                        "output_price": 0.0,
                                        "cache_hit": 0.0,
                                        "source_url": source_url,
                                    })
                        elif "输出" in row_text and "缓存" not in row_text:
                            for i, p in enumerate(prices):
                                if p is not None and i < len(results):
                                    results[i]["output_price"] = p

                    if results:
                        logger.info("DeepSeek 横向表解析成功 | models=%s",
                                    [r["model"] for r in results])
                        return results

        # ---------------------------------------------------------------
        # 火山引擎纵向表格解析
        # 找"在线推理（常规）"后面的 doubao-* 行
        # 用原始行（非 pipe_rows）判断表格上下文
        # ---------------------------------------------------------------
        if "volcengine" in source_url or "doubao" in " ".join(pipe_rows):
            in_table = False
            for raw_line in lines:
                stripped = raw_line.strip()
                if "在线推理（常规）" in stripped or "大语言模型" in stripped:
                    in_table = True
                    continue
                if "在线推理（低延迟）" in stripped:
                    in_table = False
                    continue
                if not in_table:
                    continue
                if not stripped.startswith("|"):
                    continue

                cells = [c.strip() for c in stripped.split("|") if c.strip()]
                if len(cells) < 5:
                    continue

                model = cells[0]
                if not model.startswith("doubao"):
                    continue

                in_price = None
                cache_price = None
                out_price = None

                for c in cells[1:]:
                    try:
                        v = float(c)
                    except ValueError:
                        continue
                    if in_price is None:
                        in_price = v
                    elif cache_price is None:
                        cache_price = v
                    elif out_price is None:
                        out_price = v
                        break

                if in_price is not None and out_price is not None:
                    results.append({
                        "model": model,
                        "provider": "doubao",
                        "input_price": in_price,
                        "output_price": out_price,
                        "cache_hit": cache_price or 0.0,
                        "source_url": source_url,
                    })

            if results:
                logger.info("火山引擎纵向表解析成功 | models=%s",
                            [r["model"] for r in results])
                return results

        return results
