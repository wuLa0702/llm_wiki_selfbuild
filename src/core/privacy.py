"""
隐私规则管理器 — 关键词匹配 + 分类
"""
import sqlite3

from src.db.schema import CREATE_TABLES

DEFAULT_KEYWORDS: dict[str, list[str]] = {
    "emotion": ["情感", "恋爱", "失恋", "暗恋", "分手", "情侣", "配偶",
                "前任", "相亲", "表白", "心碎", "孤独感", "抑郁", "焦虑症",
                "心理诊断"],
    "financial": ["银行卡", "账户金额", "存款", "工资", "理财", "信用卡",
                  "贷款", "负债", "投资", "密码", "支付宝", "微信支付"],
    "identity": ["身份证", "手机号", "住址", "户籍", "护照", "车牌号",
                 "社保号", "学号"],
    "health": ["病历", "体检", "手术", "诊断书", "药物", "过敏史",
               "家族病史"],
}

DEFAULT_CATEGORIES = {
    "emotion": "情感与关系",
    "financial": "财务",
    "identity": "个人身份",
    "health": "健康",
    "general": "通用",
}


class PrivacyManager:
    """隐私规则管理器"""

    def __init__(self, db_path: str = "wiki.db") -> None:
        self.db_path = db_path
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """初始化表结构 + 首次写入默认规则"""
        conn = self._get_conn()
        # 建表
        conn.executescript(CREATE_TABLES)

        # 写入默认分类
        for name, label in DEFAULT_CATEGORIES.items():
            conn.execute(
                "INSERT OR IGNORE INTO privacy_categories (name, label) VALUES (?, ?)",
                (name, label),
            )

        # 写入默认关键词（仅首次初始化）
        existing = conn.execute(
            "SELECT COUNT(*) as n FROM privacy_rules WHERE is_default = 1"
        ).fetchone()
        if existing and existing["n"] == 0:
            for category, keywords in DEFAULT_KEYWORDS.items():
                for kw in keywords:
                    conn.execute(
                        "INSERT OR IGNORE INTO privacy_rules (keyword, category, is_default) "
                        "VALUES (?, ?, 1)",
                        (kw, category),
                    )
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_rule(self, keyword: str, category: str = "general") -> None:
        """添加自定义规则"""
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO privacy_rules (keyword, category, is_default) "
            "VALUES (?, ?, 0)",
            (keyword, category),
        )
        conn.commit()
        conn.close()

    def remove_rule(self, keyword: str) -> None:
        """删除规则（仅删除用户自定义的，默认规则标记为覆盖）"""
        conn = self._get_conn()
        conn.execute("DELETE FROM privacy_rules WHERE keyword = ? AND is_default = 0", (keyword,))
        conn.commit()
        conn.close()

    def list_rules(self) -> list[dict]:
        """列出所有规则"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT r.*, c.label as category_label FROM privacy_rules r "
            "LEFT JOIN privacy_categories c ON r.category = c.name "
            "ORDER BY r.is_default DESC, r.keyword"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def match(self, content: str) -> list[dict]:
        """
        检测内容命中的隐私规则

        Args:
            content: 要检测的文本内容（源文件内容）

        Returns:
            [{"keyword": "恋爱", "category": "emotion"}, ...]
            空列表表示未命中任何隐私规则
        """
        conn = self._get_conn()
        rules = conn.execute("SELECT keyword, category FROM privacy_rules").fetchall()
        conn.close()

        results: list[dict] = []
        seen: set[str] = set()

        for rule in rules:
            if rule["keyword"] in content and rule["keyword"] not in seen:
                results.append({
                    "keyword": rule["keyword"],
                    "category": rule["category"],
                })
                seen.add(rule["keyword"])

        return results
