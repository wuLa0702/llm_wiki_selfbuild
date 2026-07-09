"""通用响应模型（健康检查、Watcher、队列、文件导入、隐私规则）"""
from pydantic import BaseModel


class RootResponse(BaseModel):
    """根路径问候"""
    message: str = "LLM Wiki is running"
    version: str = "0.1.0"


class HealthResponse(BaseModel):
    """健康检查"""
    status: str = "ok"


class WatcherStatusResponse(BaseModel):
    """Source 监听器状态"""
    running: bool = False
    detail: str | dict = ""


class QueueProgressResponse(BaseModel):
    """摄入队列进度"""
    total: int = 0
    pending: int = 0
    processing: int = 0
    done: int = 0
    failed: int = 0
    cancelled: int = 0
    message: str = ""


class QueueActionResponse(BaseModel):
    """队列操作（cancel/retry）响应"""
    status: str = "ok"
    job_id: str = ""
    message: str = ""


class ImportErrorItem(BaseModel):
    """导入失败的错误条目"""
    file: str = ""
    error: str = ""


class FolderImportResponse(BaseModel):
    """文件夹导入结果"""
    total: int = 0
    success: int = 0
    skipped: int = 0
    failed: int = 0
    pages_created: int = 0
    pages_updated: int = 0
    errors: list[dict] = []
    folder_name: str = ""


class FolderImportAsyncResponse(BaseModel):
    """异步文件夹导入结果"""
    total: int = 0
    enqueued: int = 0
    job_ids: list[str] = []
    folder_name: str = ""


class PrivacyRuleListResponse(BaseModel):
    """隐私规则列表"""
    rules: list = []


class PrivacyRuleResponse(BaseModel):
    """隐私规则操作结果"""
    status: str = "ok"
    keyword: str = ""
    category: str = ""


class LintResponse(BaseModel):
    """Lint 检查结果"""
    summary: dict = {}
    # 以下字段由静态 lint 或语义 lint 动态填充
    broken_links: list = []
    orphan_pages: list = []
    index_gaps: list = []
    contradictions: list = []
    knowledge_gaps: list = []
    shallow_pages: list = []
