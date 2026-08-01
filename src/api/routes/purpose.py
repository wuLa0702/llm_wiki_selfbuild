"""
路由: Purpose 方向管理 — /v1/purpose/*
"""
import logging
import os
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.utils.path_resolver import get_app_dir, get_raw_dir, get_wiki_dir

logger = logging.getLogger("api.routes.purpose")
router = APIRouter(tags=["purpose"])


def _purpose_file() -> str:
    return os.path.join(get_app_dir(), "purpose.md")


DEFAULT_DIRECTIONS = {
    "reading_notes": {
        "label": "📖 读书笔记",
        "description": "整理书籍阅读笔记、书评、知识卡片",
        "hint": "侧重提炼书籍核心观点、金句摘录、个人感悟",
    },
    "meeting_minutes": {
        "label": "📋 办公会议",
        "description": "管理会议纪要、决策记录、行动计划",
        "hint": "侧重会议结论、待办事项、参与者分工",
    },
    "personal_growth": {
        "label": "🌱 个人成长",
        "description": "记录学习方法、习惯养成、目标追踪",
        "hint": "侧重行为心理学、自我管理、复盘反思",
    },
    "tech_docs": {
        "label": "💻 技术文档",
        "description": "维护技术笔记、API 文档、架构设计",
        "hint": "侧重技术原理、代码示例、最佳实践",
    },
    "academic": {
        "label": "🎓 学术研究",
        "description": "管理文献综述、实验记录、论文笔记",
        "hint": "侧重文献引用、方法论、数据结论",
    },
    "project_management": {
        "label": "📊 项目管理",
        "description": "跟踪项目进度、需求文档、复盘总结",
        "hint": "侧重里程碑、风险评估、资源分配",
    },
}


class DirectionInfo(BaseModel):
    label: str
    description: str
    hint: str


class DirectionsResponse(BaseModel):
    directions: dict[str, DirectionInfo]


class GenerateRequest(BaseModel):
    direction: str


class PurposeResponse(BaseModel):
    content: str = ""
    exists: bool = False


class PurposeUpdateRequest(BaseModel):
    content: str


@router.get("/v1/purpose/directions", response_model=DirectionsResponse)
async def list_directions():
    return DirectionsResponse(
        directions={k: DirectionInfo(**v) for k, v in DEFAULT_DIRECTIONS.items()}
    )


@router.post("/v1/purpose/generate", response_model=PurposeResponse)
async def generate_purpose(body: GenerateRequest):
    if body.direction not in DEFAULT_DIRECTIONS:
        return JSONResponse(
            status_code=400,
            content={"error": f"未知方向: {body.direction}，可选: {list(DEFAULT_DIRECTIONS.keys())}"},
        )

    dir_info = DEFAULT_DIRECTIONS[body.direction]
    content = f"""# 项目宗旨（Purpose）

> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}
> 方向：{dir_info['label']}

## 定位

{dir_info['description']}。

## 关注方向

{dir_info['hint']}。
"""

    pf = _purpose_file()
    os.makedirs(os.path.dirname(pf), exist_ok=True)
    with open(pf, "w", encoding="utf-8") as f:
        f.write(content)

    return PurposeResponse(content=content, exists=True)


@router.get("/v1/purpose", response_model=PurposeResponse)
async def read_purpose():
    pf = _purpose_file()
    if not os.path.exists(pf):
        return PurposeResponse(content="", exists=False)
    with open(pf, "r", encoding="utf-8") as f:
        return PurposeResponse(content=f.read(), exists=True)


@router.put("/v1/purpose", response_model=PurposeResponse)
async def update_purpose(body: PurposeUpdateRequest):
    pf = _purpose_file()
    os.makedirs(os.path.dirname(pf), exist_ok=True)
    with open(pf, "w", encoding="utf-8") as f:
        f.write(body.content)
    return PurposeResponse(content=body.content, exists=True)

# ------------------------------------------------------------------
# 文件树
# ------------------------------------------------------------------

class FileTreeItem(BaseModel):
    type: str
    size: int = 0


FileTreeResponse = dict[str, "FileTreeItem | dict"]


def _build_tree(base_dir: str) -> dict:
    result = {}
    if not os.path.isdir(base_dir):
        return result
    try:
        items = []
        for name in os.listdir(base_dir):
            full = os.path.join(base_dir, name)
            if name.startswith("."):
                continue
            if os.path.isdir(full):
                children = _build_tree(full)
                items.append((name, {"type": "directory", "children": children}))
            elif name.endswith(".md") or name.endswith(".txt"):
                stat = os.stat(full)
                items.append((name, {"type": "file", "size": stat.st_size, "mtime": int(stat.st_mtime)}))
        items.sort(key=lambda x: (0 if x[1]["type"] == "directory" else 1, x[1].get("mtime", 0)))
        for name, data in items:
            result[name] = data
    except PermissionError:
        pass
    return result


@router.get("/v1/file-tree")
async def get_file_tree():
    tree = {}

    wiki_dir = get_wiki_dir()
    if os.path.isdir(wiki_dir):
        tree["wiki"] = {"type": "directory", "children": _build_tree(wiki_dir)}

    raw_dir = get_raw_dir()
    if os.path.isdir(raw_dir):
        tree["raw"] = {"type": "directory", "children": _build_tree(raw_dir)}

    pf = _purpose_file()
    if os.path.exists(pf):
        tree["purpose.md"] = {"type": "file", "size": os.path.getsize(pf)}

    return tree


def _resolve_display_path(path: str) -> tuple[str | None, int | None]:
    """将前端路径 (wiki/xxx, raw/xxx, purpose.md) 解析为绝对路径。

    Returns:
        (abs_path, None) 或 (None, status_code)
    """
    # normpath 统一分隔符（修复 2026-08-01：Path.cwd() 返回正斜杠、
    # os.path.join 返回反斜杠，混合分隔符导致 startswith 误判 403）
    wiki_dir = os.path.normpath(get_wiki_dir())
    raw_dir = os.path.normpath(get_raw_dir())
    app_dir = os.path.normpath(get_app_dir())

    if path == "purpose.md":
        return os.path.join(app_dir, "purpose.md"), None

    if path.startswith("wiki/"):
        rel = path[5:]
        abs_path = os.path.normpath(os.path.join(wiki_dir, rel))
        if not abs_path.startswith(wiki_dir):
            return None, 403
        return abs_path, None

    if path.startswith("raw/"):
        rel = path[4:]
        abs_path = os.path.normpath(os.path.join(raw_dir, rel))
        if not abs_path.startswith(raw_dir):
            return None, 403
        return abs_path, None

    # 兼容旧版文件树返回的 sources/xxx 格式（2026-08-01 起 tree 返回 raw/sources/xxx）
    if path.startswith("sources/"):
        rel = path[len("sources/"):]
        abs_path = os.path.normpath(os.path.join(raw_dir, "sources", rel))
        if not abs_path.startswith(os.path.normpath(os.path.join(raw_dir, "sources"))):
            return None, 403
        return abs_path, None

    return None, 403


@router.get("/v1/file-content")
async def get_file_content(path: str):
    abs_path, err = _resolve_display_path(path)
    if err:
        return JSONResponse(status_code=err, content={"error": "Access denied"})

    assert abs_path is not None

    if not os.path.exists(abs_path):
        return JSONResponse(status_code=404, content={"error": "File not found"})

    try:
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"path": path, "content": content, "size": os.path.getsize(abs_path)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


class FileWriteRequest(BaseModel):
    path: str
    content: str


@router.post("/v1/file-content")
async def write_file_content(body: FileWriteRequest):
    abs_path, err = _resolve_display_path(body.path)
    if err:
        return JSONResponse(status_code=err, content={"error": "Access denied"})

    assert abs_path is not None

    try:
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(body.content)
        return {"status": "ok", "path": body.path}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
