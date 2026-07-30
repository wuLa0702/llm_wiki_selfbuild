"""
数据访问层 — SQLite 操作
"""
import json
import sqlite3

from src.utils.path_resolver import get_db_path


class WikiRepository:
    """Wiki 元数据的数据访问层"""

    def __init__(self, db_path: str | None = None) -> None:
        """
        Args:
            db_path: SQLite 数据库文件路径（支持 :memory: 用于测试）。
                     None 时默认使用用户数据目录下的 wiki.db。
        """
        self.db_path = db_path if db_path is not None else get_db_path("wiki.db")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        """初始化数据库表"""
        from src.db.schema import CREATE_TABLES

        conn = self._get_connection()
        conn.executescript(CREATE_TABLES)
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @staticmethod
    def _tags_to_json(tags: list[str] | None) -> str:
        """将标签列表序列化为 JSON 字符串"""
        return json.dumps(tags or [], ensure_ascii=False)

    @staticmethod
    def _tags_from_json(raw: str) -> list[str]:
        """从 JSON 字符串反序列化标签列表"""
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    def _log_operation(self, action: str, detail: dict | None = None) -> None:
        """记录操作到 operation_log"""
        conn = self._get_connection()
        conn.execute(
            "INSERT INTO operation_log (action, detail) VALUES (?, ?)",
            (action, json.dumps(detail or {}, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # 页面 CRUD
    # ------------------------------------------------------------------

    def add_page(
        self,
        path: str,
        title: str,
        page_type: str,
        tags: list[str] | None = None,
        word_count: int = 0,
    ) -> None:
        """
        添加或更新页面记录（UPSERT）

        Args:
            path: 页面相对路径，如 "entities/python.md"
            title: 页面标题
            page_type: 类型（entity / concept / source / query）
            tags: 标签列表
            word_count: 字数
        """
        conn = self._get_connection()
        tags_json = self._tags_to_json(tags)
        conn.execute(
            """
            INSERT OR REPLACE INTO wiki_pages
                (path, title, page_type, tags, word_count, updated_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (path, title, page_type, tags_json, word_count),
        )
        conn.commit()
        conn.close()

        self._log_operation("add_page", {"path": path, "title": title})

    def add_link(self, source: str, target: str) -> None:
        """
        添加页面间链接关系（已存在则忽略）

        Args:
            source: 来源页面路径
            target: 目标页面路径
        """
        conn = self._get_connection()
        conn.execute(
            "INSERT OR IGNORE INTO page_links (source_path, target_path) VALUES (?, ?)",
            (source, target),
        )
        conn.commit()
        conn.close()

        self._log_operation("add_link", {"source": source, "target": target})

    def get_page(self, path: str) -> dict | None:
        """
        获取页面信息（含反向链接）

        Args:
            path: 页面路径

        Returns:
            页面字典，不存在则返回 None
        """
        conn = self._get_connection()

        row = conn.execute(
            "SELECT * FROM wiki_pages WHERE path = ?", (path,)
        ).fetchone()

        if row is None:
            conn.close()
            return None

        # 转为 dict
        result = dict(row)
        result["tags"] = self._tags_from_json(result["tags"])

        # 反向链接：哪些页面指向了当前页面
        backlinks = conn.execute(
            "SELECT source_path FROM page_links WHERE target_path = ?",
            (path,),
        ).fetchall()
        result["backlinks"] = [r["source_path"] for r in backlinks]

        # 正向链接：当前页面指向了哪些页面
        forward = conn.execute(
            "SELECT target_path FROM page_links WHERE source_path = ?",
            (path,),
        ).fetchall()
        result["links"] = [r["target_path"] for r in forward]

        conn.close()
        return result

    def search_pages(self, keyword: str, limit: int = 20) -> list[dict]:
        """
        搜索页面（SQLite LIKE）

        Args:
            keyword: 搜索关键词（大小写不敏感）
            limit: 最大返回条数

        Returns:
            匹配的页面列表，每项包含 {path, title, page_type, tags, updated_at}
        """
        conn = self._get_connection()
        pattern = f"%{keyword}%"
        rows = conn.execute(
            """
            SELECT path, title, page_type, tags, updated_at
            FROM wiki_pages
            WHERE title LIKE ? OR path LIKE ? OR tags LIKE ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (pattern, pattern, pattern, limit),
        ).fetchall()

        result = []
        for r in rows:
            d = dict(r)
            d["tags"] = self._tags_from_json(d["tags"])
            result.append(d)

        conn.close()
        return result

    # ------------------------------------------------------------------
    # 4-Signal 关联度
    # ------------------------------------------------------------------

    def save_relevance(self, rows: list[dict]) -> None:
        """
        批量写入关联度数据（UPSERT）

        Args:
            rows: [{source_path, target_path, total_score, direct_link,
                    source_overlap, adamic_adar, type_affinity}, ...]
        """
        conn = self._get_connection()
        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO graph_relevance
                    (source_path, target_path, total_score,
                     direct_link, source_overlap, adamic_adar, type_affinity)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["source_path"], row["target_path"],
                    row["total_score"],
                    row.get("direct_link", 0),
                    row.get("source_overlap", 0),
                    row.get("adamic_adar", 0),
                    row.get("type_affinity", 0),
                ),
            )
        conn.commit()
        conn.close()

    def get_related_pages(self, path: str, limit: int = 20) -> list[dict]:
        """
        返回与指定页面最相关的页面（按 total_score 降序）

        Args:
            path: 页面路径
            limit: 最多返回条数

        Returns:
            [{target_path, total_score, direct_link, source_overlap,
              adamic_adar, type_affinity}, ...]
        """
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT target_path, total_score, direct_link,
                   source_overlap, adamic_adar, type_affinity
            FROM graph_relevance
            WHERE source_path = ?
            ORDER BY total_score DESC
            LIMIT ?
            """,
            (path, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_all_relevance(self) -> list[dict]:
        """
        返回 graph_relevance 表的所有行（用于社区检测等全量分析）

        Returns:
            [{source_path, target_path, total_score, direct_link,
              source_overlap, adamic_adar, type_affinity}, ...]
        """
        conn = self._get_connection()
        rows = conn.execute(
            """
            SELECT source_path, target_path, total_score,
                   direct_link, source_overlap, adamic_adar, type_affinity
            FROM graph_relevance
            ORDER BY total_score DESC
            """
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_referencing_pages(self, path: str) -> list[str]:
        """
        返回所有引用了指定页面的文档路径列表

        Args:
            path: 目标页面路径

        Returns:
            引用该页面的源页面路径列表
        """
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT source_path FROM page_links WHERE target_path = ?",
            (path,),
        ).fetchall()
        conn.close()
        return [r["source_path"] for r in rows]

    def get_orphan_pages(self) -> list[str]:
        """获取孤儿页（Phase 2 实现）"""
        raise NotImplementedError("Phase 2 实现")

    # ------------------------------------------------------------------
    # Wiki 设置（密码等）
    # ------------------------------------------------------------------

    def get_setting(self, key: str) -> str | None:
        """获取 Wiki 设置值

        Args:
            key: 设置键名

        Returns:
            设置值，不存在返回 None
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT value FROM wiki_settings WHERE key = ?", (key,)
        ).fetchone()
        conn.close()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        """设置 Wiki 设置（UPSERT）

        Args:
            key: 设置键名
            value: 设置值
        """
        conn = self._get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO wiki_settings (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, value),
        )
        conn.commit()
        conn.close()

    def delete_setting(self, key: str) -> None:
        """删除 Wiki 设置

        Args:
            key: 设置键名
        """
        conn = self._get_connection()
        conn.execute("DELETE FROM wiki_settings WHERE key = ?", (key,))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # 语义 Lint 缓存
    # ------------------------------------------------------------------

    def get_lint_cache(self, cache_key: str = "semantic_lint") -> dict | None:
        """读取语义 Lint 缓存

        Args:
            cache_key: 缓存键

        Returns:
            缓存结果 dict，不存在返回 None
        """
        conn = self._get_connection()
        row = conn.execute(
            "SELECT result_json FROM lint_cache WHERE cache_key = ?", (cache_key,)
        ).fetchone()
        conn.close()
        if row is None:
            return None
        try:
            return json.loads(row["result_json"])
        except (json.JSONDecodeError, TypeError):
            return None

    def save_lint_cache(self, result: dict, cache_key: str = "semantic_lint") -> None:
        """写入语义 Lint 缓存（UPSERT）

        Args:
            result: 缓存结果 dict
            cache_key: 缓存键
        """
        conn = self._get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO lint_cache (cache_key, result_json, created_at) VALUES (?, ?, datetime('now'))",
            (cache_key, json.dumps(result, ensure_ascii=False)),
        )
        conn.commit()
        conn.close()

    def clear_lint_cache(self, cache_key: str = "semantic_lint") -> None:
        """删除语义 Lint 缓存

        Args:
            cache_key: 缓存键（默认 semantic_lint）
        """
        conn = self._get_connection()
        conn.execute("DELETE FROM lint_cache WHERE cache_key = ?", (cache_key,))
        conn.commit()
        conn.close()

    # ------------------------------------------------------------------
    # 模型自定义配置 (model_configs)
    # ------------------------------------------------------------------

    def list_model_configs(self) -> list[dict]:
        """列出全部模型配置"""
        conn = self._get_connection()
        rows = conn.execute(
            "SELECT * FROM model_configs ORDER BY sort_order ASC, id ASC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_model_config(self, config_id: int) -> dict | None:
        """获取单个模型配置"""
        conn = self._get_connection()
        row = conn.execute(
            "SELECT * FROM model_configs WHERE id = ?", (config_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def create_model_config(self, data: dict) -> int:
        """创建模型配置，返回新 id"""
        conn = self._get_connection()
        cur = conn.execute(
            """INSERT INTO model_configs (name, provider, model_name, api_key, api_base, is_active, sort_order)
               VALUES (:name, :provider, :model_name, :api_key, :api_base, :is_active, :sort_order)""",
            {
                "name": data.get("name", ""),
                "provider": data.get("provider", "custom"),
                "model_name": data.get("model_name", ""),
                "api_key": data.get("api_key", ""),
                "api_base": data.get("api_base", ""),
                "is_active": 1 if data.get("is_active") else 0,
                "sort_order": int(data.get("sort_order", 0)),
            },
        )
        new_id = cur.lastrowid
        conn.commit()
        conn.close()
        return new_id

    def update_model_config(self, config_id: int, data: dict) -> bool:
        """更新模型配置"""
        allowed = {"name", "provider", "model_name", "api_key", "api_base", "is_active", "sort_order"}
        sets = []
        params: dict = {}
        for k, v in data.items():
            if k in allowed:
                sets.append(f"{k} = :{k}")
                if k == "is_active":
                    params[k] = 1 if v else 0
                elif k == "sort_order":
                    params[k] = int(v)
                else:
                    params[k] = v
        if not sets:
            return False
        sets.append("updated_at = datetime('now')")
        params["id"] = config_id
        sql = f"UPDATE model_configs SET {', '.join(sets)} WHERE id = :id"
        conn = self._get_connection()
        cur = conn.execute(sql, params)
        conn.commit()
        conn.close()
        return cur.rowcount > 0

    def delete_model_config(self, config_id: int) -> bool:
        """删除模型配置"""
        conn = self._get_connection()
        cur = conn.execute("DELETE FROM model_configs WHERE id = ?", (config_id,))
        conn.commit()
        conn.close()
        return cur.rowcount > 0
