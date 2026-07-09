"""
应用级全局状态 — 生命周期管理的共享单例

只存放需要跨请求共享的后台服务实例：
  - TaskQueue：后台任务调度
  - IngestQueue：摄入队列
  - SourceWatcher：源文件监听

依赖方向：app_state → core（引 ingest_queue、task_queue、watcher、graph）
不存放工厂函数（路由直接构造 core 实例）。
不存放配置（从 config 读取）。
"""
import logging

from src.config import settings
from src.core.graph import rebuild_graph
from src.core.ingest import IngestQueue
from src.core.task_queue import TaskQueue
from src.core.watcher import SourceWatcher

logger = logging.getLogger("app_state")

# ====================================================================
# 全局服务实例
# ====================================================================

_watcher: SourceWatcher | None = None
_task_queue: TaskQueue | None = None
_ingest_queue: IngestQueue | None = None


def get_task_queue() -> TaskQueue | None:
    return _task_queue


def get_ingest_queue() -> IngestQueue | None:
    return _ingest_queue


def get_watcher() -> SourceWatcher | None:
    return _watcher


def set_watcher(watcher: SourceWatcher | None) -> None:
    """设置 _watcher 实例（供 watcher/start 路由在运行时重建）"""
    global _watcher
    _watcher = watcher


# ====================================================================
# 生命周期
# ====================================================================


def init_services() -> None:
    """服务启动时初始化后台服务（TaskQueue → IngestQueue → Watcher）"""
    global _watcher, _task_queue, _ingest_queue

    _task_queue = TaskQueue()
    _task_queue.register_handler("rebuild_graph", rebuild_graph)
    _task_queue.start()

    _ingest_queue = IngestQueue(task_queue=_task_queue)
    _ingest_queue.start()

    if not settings.watcher_enabled:
        logger.info("SourceWatcher 已禁用（WATCHER_ENABLED=false）")
        return

    _watcher = SourceWatcher(task_queue=_task_queue)
    _watcher.start()


def shutdown_services() -> None:
    """服务关闭时依次停止后台服务"""
    global _watcher, _task_queue, _ingest_queue

    if _ingest_queue:
        _ingest_queue.stop()
    if _task_queue:
        _task_queue.stop()
    if _watcher and _watcher.is_running:
        _watcher.stop()
