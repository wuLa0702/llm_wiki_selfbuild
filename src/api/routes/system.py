"""
路由: 系统管理 — /v1/system/*
"""
import logging
import os
import shutil

from fastapi import APIRouter

from src.utils.path_resolver import get_app_dir, get_db_path, get_raw_sources_dir, get_wiki_dir, is_frozen

logger = logging.getLogger("api.routes.system")
router = APIRouter(tags=["system"])


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
