"""
路由: 系统管理 — /v1/system/*
"""
import logging
import os
import shutil

from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger("api.routes.system")
router = APIRouter(tags=["system"])

TEMPLATES_DIR = "src/templates"
WIKI_DIR = "wiki"
SOURCES_DIR = "raw/sources"
DB_FILE = "wiki.db"
PURPOSE_FILE = "purpose.md"
SCHEMA_FILE = "wiki/wiki-schema.md"


@router.post("/v1/system/reset")
async def reset_system():
    """重置初始化：清空 wiki + DB + raw/sources，重新生成模板文件"""
    logger.warning("系统重置开始 — 清空所有数据")

    # 1. 清空 wiki/ 目录（保留目录本身）
    if os.path.isdir(WIKI_DIR):
        for name in os.listdir(WIKI_DIR):
            full = os.path.join(WIKI_DIR, name)
            try:
                if os.path.isfile(full) or os.path.islink(full):
                    os.remove(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full)
            except Exception as e:
                logger.error("删除 %s 失败: %s", full, e)

    # 2. 清空 raw/sources/ 目录
    if os.path.isdir(SOURCES_DIR):
        for name in os.listdir(SOURCES_DIR):
            full = os.path.join(SOURCES_DIR, name)
            try:
                if os.path.isfile(full) or os.path.islink(full):
                    os.remove(full)
                elif os.path.isdir(full):
                    shutil.rmtree(full)
            except Exception as e:
                logger.error("删除 %s 失败: %s", full, e)

    # 3. 删除 wiki.db
    if os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
            # 也删除 journal/wal 等附属文件
            for ext in [".db-journal", ".db-wal", ".db-shm"]:
                j = DB_FILE + ext
                if os.path.exists(j):
                    os.remove(j)
        except Exception as e:
            logger.error("删除 %s 失败: %s", DB_FILE, e)

    # 4. 从模板重新生成 purpose.md
    template_purpose = os.path.join(TEMPLATES_DIR, "purpose.md.default")
    if os.path.exists(template_purpose):
        try:
            with open(template_purpose, "r", encoding="utf-8") as f:
                content = f.read()
            with open(PURPOSE_FILE, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("已生成 %s", PURPOSE_FILE)
        except Exception as e:
            logger.error("生成 %s 失败: %s", PURPOSE_FILE, e)

    # 5. 从模板重新生成 wiki/wiki-schema.md
    os.makedirs("wiki", exist_ok=True)
    template_schema = os.path.join(TEMPLATES_DIR, "wiki-schema.md.default")
    if os.path.exists(template_schema):
        try:
            with open(template_schema, "r", encoding="utf-8") as f:
                content = f.read()
            with open(SCHEMA_FILE, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("已生成 %s", SCHEMA_FILE)
        except Exception as e:
            logger.error("生成 %s 失败: %s", SCHEMA_FILE, e)

    logger.warning("系统重置完成")
    return {"status": "ok", "message": "已重置，请手动重启服务"}
