"""
路由: 系统管理 — /v1/system/*
"""
import logging
import os
import shutil
import sqlite3

from fastapi import APIRouter

from src.utils.path_resolver import get_app_dir, get_db_path, get_raw_sources_dir, get_wiki_dir, is_frozen

logger = logging.getLogger("api.routes.system")
router = APIRouter(tags=["system"])

# wiki.db 中属于「数据文件」的表（reset-data 时清空行，保留表结构）
# 配置表（wiki_settings / model_configs / privacy_rules / privacy_categories / model_pricing）不在其中
DATA_TABLES = [
    "wiki_pages",
    "page_links",
    "ingest_queue",
    "task_queue",
    "graph_cache",
    "graph_relevance",
    "ingest_cache",
    "lint_cache",
    "token_usage_log",
    "operation_log",
]

# agent_persistence.db（Agent 对话记忆）的全部表
AGENT_MEMORY_TABLES = [
    "agent_threads",
    "thread_messages",
    "thread_entities",
    "global_entities",
    "agent_feedback",
]

# checkpoints.db（LangGraph checkpoint，遗留表）
CHECKPOINT_TABLES = ["checkpoints", "writes"]


def _clear_db_tables(db_path: str, tables: list[str]) -> None:
    """清空指定 SQLite 库的全部数据表（保留表结构与连接持有者兼容）

    注意：不能直接删文件——运行中的实例持有连接时，Windows 下
    文件被删除后会被持有进程重新创建并写回旧数据（表级清理则无此问题）。
    """
    if not os.path.exists(db_path):
        return
    try:
        con = sqlite3.connect(db_path)
        with con:
            for table in tables:
                con.execute(f"DELETE FROM {table}")
            # 重置自增序列（库无 sqlite_sequence 表时跳过，不影响清理结果）
            try:
                con.execute("DELETE FROM sqlite_sequence")
            except sqlite3.OperationalError:
                pass
        con.close()
        logger.info("已清空 %s 数据表: %s", db_path, ", ".join(tables))
    except Exception as e:
        logger.error("清空 %s 失败: %s", db_path, e)


def _get_templates_dir() -> str:
    """模板目录：开发模式在 src/templates，打包模式在 exe 内部"""
    if is_frozen():
        import sys
        return os.path.join(sys._MEIPASS, "src", "templates")  # type: ignore[attr-defined]
    return os.path.join(os.getcwd(), "src", "templates")


@router.post("/v1/system/reset")
async def reset_system():
    """重置初始化：清空 wiki + DB + raw/sources，重新生成模板文件"""
    logger.warning("系统重置开始 — 清空所有数据")

    wiki_dir = get_wiki_dir()
    sources_dir = get_raw_sources_dir()
    db_file = get_db_path("wiki.db")
    purpose_file = os.path.join(get_app_dir(), "purpose.md")
    schema_file = os.path.join(wiki_dir, "wiki-schema.md")
    templates_dir = _get_templates_dir()

    # 1. 清空 wiki/ 目录（保留目录本身）
    if os.path.isdir(wiki_dir):
        for name in os.listdir(wiki_dir):
            full = os.path.join(wiki_dir, name)
            try:
                if os.path.isfile(full) or os.path.islink(full):
                    os.remove(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full)
            except Exception as e:
                logger.error("删除 %s 失败: %s", full, e)

    # 2. 清空 raw/sources/ 目录
    if os.path.isdir(sources_dir):
        for name in os.listdir(sources_dir):
            full = os.path.join(sources_dir, name)
            try:
                if os.path.isfile(full) or os.path.islink(full):
                    os.remove(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full)
            except Exception as e:
                logger.error("删除 %s 失败: %s", full, e)

    # 3. 删除 wiki.db
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
            # 也删除 journal/wal 等附属文件
            for ext in [".db-journal", ".db-wal", ".db-shm"]:
                j = db_file + ext
                if os.path.exists(j):
                    os.remove(j)
        except Exception as e:
            logger.error("删除 %s 失败: %s", db_file, e)

    # 4. 从模板重新生成 purpose.md
    template_purpose = os.path.join(templates_dir, "purpose.md.default")
    if os.path.exists(template_purpose):
        try:
            with open(template_purpose, "r", encoding="utf-8") as f:
                content = f.read()
            os.makedirs(os.path.dirname(purpose_file), exist_ok=True)
            with open(purpose_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("已生成 %s", purpose_file)
        except Exception as e:
            logger.error("生成 %s 失败: %s", purpose_file, e)

    # 5. 从模板重新生成 wiki/wiki-schema.md
    os.makedirs(wiki_dir, exist_ok=True)
    template_schema = os.path.join(templates_dir, "wiki-schema.md.default")
    if os.path.exists(template_schema):
        try:
            with open(template_schema, "r", encoding="utf-8") as f:
                content = f.read()
            with open(schema_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("已生成 %s", schema_file)
        except Exception as e:
            logger.error("生成 %s 失败: %s", schema_file, e)

    logger.warning("系统重置完成")
    return {"status": "ok", "message": "已重置，请手动重启服务"}


@router.post("/v1/system/reset-data")
async def reset_data():
    """重置数据文件：清空 Wiki 页面/队列/对话历史/向量索引，保留系统配置（API 密钥/模型配置/schema）"""
    logger.warning("重置数据文件开始 — 清空数据，保留配置")

    wiki_dir = get_wiki_dir()
    sources_dir = get_raw_sources_dir()
    db_file = get_db_path("wiki.db")
    app_dir = get_app_dir()

    # 1. 清空 wiki/ 目录（保留 wiki-schema.md 构建规范）
    if os.path.isdir(wiki_dir):
        for name in os.listdir(wiki_dir):
            if name == "wiki-schema.md":
                continue
            full = os.path.join(wiki_dir, name)
            try:
                if os.path.isfile(full) or os.path.islink(full):
                    os.remove(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full)
            except Exception as e:
                logger.error("删除 %s 失败: %s", full, e)

    # 2. 清空 raw/sources/ 目录（用户输入文件）
    if os.path.isdir(sources_dir):
        for name in os.listdir(sources_dir):
            full = os.path.join(sources_dir, name)
            try:
                if os.path.isfile(full) or os.path.islink(full):
                    os.remove(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full)
            except Exception as e:
                logger.error("删除 %s 失败: %s", full, e)

    # 3. wiki.db 表级清理（保留 wiki_settings/model_configs 等配置表）
    _clear_db_tables(db_file, DATA_TABLES)

    # 4. 对话记忆 / checkpoint 表级清理（不能删文件，见 _clear_db_tables 注释）
    _clear_db_tables(get_db_path("agent_persistence.db"), AGENT_MEMORY_TABLES)
    _clear_db_tables(get_db_path("checkpoints.db"), CHECKPOINT_TABLES)

    # 5. 删除向量索引目录（embedding 懒加载，重启后自动重建）
    chroma_dir = os.path.join(app_dir, "chroma_db")
    if os.path.isdir(chroma_dir):
        try:
            shutil.rmtree(chroma_dir)
            logger.info("已删除向量索引目录 %s", chroma_dir)
        except Exception as e:
            logger.error("删除 %s 失败: %s", chroma_dir, e)

    logger.warning("重置数据文件完成")
    return {"status": "ok", "message": "数据文件已重置，请手动重启服务"}
