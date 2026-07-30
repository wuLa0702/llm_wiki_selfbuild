"""
LLM Wiki — 应用启动入口（PyInstaller 打包用）

职责：
  - 导入 app 实例
  - 启动 uvicorn 服务器
  - 打包模式下自动打开浏览器
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
from src.utils.path_resolver import is_frozen

logger = logging.getLogger("launcher")

HOST = "127.0.0.1"
PORT = 8766


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 打包模式：启动后自动打开浏览器
    if is_frozen():
        logger.info("PyInstaller 打包模式 — 启动后自动打开浏览器")
        _auto_open_browser()

    logger.info("启动 uvicorn | host=%s port=%d", HOST, PORT)
    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="warning",
        reload=False,  # 打包模式禁用热重载
    )


def _auto_open_browser():
    """延迟 2 秒后自动打开浏览器"""
    import threading
    timer = threading.Timer(2.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}"))
    timer.daemon = True
    timer.start()


if __name__ == "__main__":
    main()
