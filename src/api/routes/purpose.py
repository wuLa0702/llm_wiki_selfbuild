"""
路由: Purpose 方向管理 — /v1/purpose/*
"""
import logging
import os
from datetime import datetime

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logger = logging.getLogger("api.routes.purpose")
router = APIRouter(tags=["purpose"])

PURPOSE_FILE = "purpose.md"
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
    """方向信息"""
    label: str
    description: str
    hint: str


class DirectionsResponse(BaseModel):
    """可用方向列表"""
    directions: dict[str, DirectionInfo]


class GenerateRequest(BaseModel):
    """生成 purpose 请求"""
    direction: str


class PurposeResponse(BaseModel):
    """purpose 响应"""
    content: str = ""
    exists: bool = False


class PurposeUpdateRequest(BaseModel):
    """更新 purpose 请求"""
    content: str


@router.get("/v1/purpose/directions", response_model=DirectionsResponse)
async def list_directions():
    """获取可选的 Wiki 方向列表"""
    return DirectionsResponse(
        directions={k: DirectionInfo(**v) for k, v in DEFAULT_DIRECTIONS.items()}
    )


@router.post("/v1/purpose/generate", response_model=PurposeResponse)
async def generate_purpose(body: GenerateRequest):
    """根据选择的方向生成 purpose.md"""
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

    with open(PURPOSE_FILE, "w", encoding="utf-8") as f:
        f.write(content)

    return PurposeResponse(content=content, exists=True)


@router.get("/v1/purpose", response_model=PurposeResponse)
async def read_purpose():
    """读取当前 purpose.md"""
    if not os.path.exists(PURPOSE_FILE):
        return PurposeResponse(content="", exists=False)
    with open(PURPOSE_FILE, "r", encoding="utf-8") as f:
        return PurposeResponse(content=f.read(), exists=True)


@router.put("/v1/purpose", response_model=PurposeResponse)
async def update_purpose(body: PurposeUpdateRequest):
    """直接更新 purpose.md 内容"""
    with open(PURPOSE_FILE, "w", encoding="utf-8") as f:
        f.write(body.content)
    return PurposeResponse(content=body.content, exists=True)

# ------------------------------------------------------------------
# 文件树
# ------------------------------------------------------------------

class FileTreeItem(BaseModel):
    """文件树节点"""
    type: str  # "file" | "directory"
    size: int = 0


FileTreeResponse = dict[str, "FileTreeItem | dict"]

def _build_tree(base_dir: str) -> dict:
    """递归构建目录树"""
    result = {}
    if not os.path.isdir(base_dir):
        return result
    try:
        for name in sorted(os.listdir(base_dir)):
            full = os.path.join(base_dir, name)
            if name.startswith("."):
                continue
            if os.path.isdir(full):
                children = _build_tree(full)
                result[name] = {"type": "directory", "children": children}
            elif name.endswith(".md") or name.endswith(".txt"):
                result[name] = {"type": "file", "size": os.path.getsize(full)}
    except PermissionError:
        pass
    return result


@router.get("/v1/file-tree")
async def get_file_tree():
    """获取文件树（wiki/ + raw/sources/ + purpose.md）"""
    tree = {}

    # wiki/ 目录
    if os.path.isdir("wiki"):
        tree["wiki"] = {"type": "directory", "children": _build_tree("wiki")}

    # raw/sources/ 目录
    if os.path.isdir("raw/sources"):
        tree["raw/sources"] = {"type": "directory", "children": _build_tree("raw/sources")}

    # purpose.md
    if os.path.exists("purpose.md"):
        tree["purpose.md"] = {"type": "file", "size": os.path.getsize("purpose.md")}

    return tree


@router.get("/v1/file-content")
async def get_file_content(path: str):
    """读取文件内容"""
    import os

    # 安全校验：只允许读取 wiki/ raw/ purpose.md
    safe = False
    allowed_prefixes = ("wiki/", "raw/")
    if path == "purpose.md":
        safe = True
    elif any(path.startswith(p) for p in allowed_prefixes):
        # 防止路径穿越
        full = os.path.normpath(path)
        if not full.startswith(".."):
            safe = True

    if not safe:
        return JSONResponse(status_code=403, content={"error": "Access denied"})

    if not os.path.exists(path):
        return JSONResponse(status_code=404, content={"error": "File not found"})

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"path": path, "content": content, "size": os.path.getsize(path)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


class FileWriteRequest(BaseModel):
    """写入文件请求"""
    path: str
    content: str


@router.post("/v1/file-content")
async def write_file_content(body: FileWriteRequest):
    """写入文件内容"""
    path = body.path
    content = body.content

    safe = False
    allowed_prefixes = ("wiki/", "raw/")
    if path == "purpose.md":
        safe = True
    elif any(path.startswith(p) for p in allowed_prefixes):
        full = os.path.normpath(path)
        if not full.startswith(".."):
            safe = True

    if not safe:
        return JSONResponse(status_code=403, content={"error": "Access denied"})

    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "ok", "path": path}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
