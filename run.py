"""
LLM Wiki — 应用启动入口（PyInstaller 打包用）

职责：
  - 导入 app 实例
  - 单实例互斥锁（防多开）
  - 启动 uvicorn 服务器
  - 打包模式下自动打开浏览器
  - 日志写入 %APPDATA%/LLM-Wiki/logs/
  - 处理 Ctrl+C 优雅退出
"""
import logging
import os
import sys
import webbrowser

import uvicorn

# 确保 src 在 sys.path 中（PyInstaller 打包后需要）
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from src.main import app
from src.utils.path_resolver import get_app_dir, get_log_dir, is_frozen

logger = logging.getLogger("launcher")

HOST = "127.0.0.1"
PORT = 8766

# 文件锁路径（防多实例）
_LOCK_FILE = os.path.join(get_app_dir(), ".run.lock")


def _acquire_lock() -> bool:
    """尝试获取文件锁

    Returns:
        True 表示成功获得锁（唯一实例）
        False 表示已有实例在运行
    """
    import socket

    try:
        lock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lock.bind((HOST, PORT))
        lock.listen(1)
        # 不解绑——保持端口占用作为锁信号
        # 进程退出时 socket 自动释放
        return True
    except OSError:
        return False


def main():
    # 日志配置（打包模式写入文件 + 控制台）
    log_dir = get_log_dir()
    log_file = os.path.join(log_dir, "app.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    # 单实例检查
    if not _acquire_lock():
        logger.warning("端口 %d 已被占用，LLM-Wiki 可能已在运行中", PORT)
        logger.warning("如需重启，请先关闭已有进程")
        _open_browser_and_exit()
        return

    logger.info("LLM-Wiki 启动 | host=%s port=%d log=%s", HOST, PORT, log_file)

    # 打包模式：启动后自动打开浏览器
    if is_frozen():
        logger.info("PyInstaller 打包模式 — 启动后自动打开浏览器")
        _auto_open_browser()

    try:
        uvicorn.run(
            app,
            host=HOST,
            port=PORT,
            log_level="warning",
            reload=False,  # 打包模式禁用热重载
            log_config=None,  # 禁止 uvicorn 默认日志（console=False 时 sys.stdout=None 会炸）
        )
    except KeyboardInterrupt:
        logger.info("收到退出信号，优雅关闭...")
    except Exception as e:
        logger.error("启动失败 | error=%s", e)
        raise
    finally:
        logger.info("LLM-Wiki 已退出")


def _open_browser_and_exit():
    """已有实例运行时：打开浏览器访问已有实例后退出"""
    import threading
    threading.Timer(0.5, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()


def _auto_open_browser():
    """延迟 2 秒后自动打开浏览器"""
    import threading
    timer = threading.Timer(2.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}"))
    timer.daemon = True
    timer.start()


if __name__ == "__main__":
    main()
