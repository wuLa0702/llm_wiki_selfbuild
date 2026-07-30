"""
LLM Wiki — 应用启动入口（PyInstaller 打包用）

职责：
  - 导入 app 实例
  - 单实例互斥锁（防多开）
  - 启动 uvicorn 服务器
  - 打包模式下自动打开浏览器
  - 日志写入 %APPDATA%/LLM-Wiki/logs/
  - 处理 Ctrl+C 优雅退出
  - 全局异常捕获（崩溃弹窗 + 日志落盘）
"""
import logging
import os
import sys
import threading
import traceback
import webbrowser

import uvicorn

# 确保 src 在 sys.path 中（PyInstaller 打包后需要）
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

HOST = "127.0.0.1"
PORT = 8766

# ── 延迟导入标志 ──
_app = None
_path_resolver = None


def _get_path_resolver():
    """延迟导入 path_resolver，避免模块级 import 失败时无日志"""
    global _path_resolver
    if _path_resolver is None:
        from src.utils.path_resolver import get_app_dir, get_log_dir, is_frozen
        _path_resolver = (get_app_dir, get_log_dir, is_frozen)
    return _path_resolver


def _get_app():
    """延迟导入 FastAPI app 实例"""
    global _app
    if _app is None:
        from src.main import app
        _app = app
    return _app


def _show_error_dialog(title: str, message: str) -> None:
    """Windows 弹窗显示致命错误（console=False 时用户唯一能看到的提示）

    开发模式（非 frozen）下不弹窗，只打印到 stderr。
    """
    if getattr(sys, "frozen", False):
        try:
            import ctypes
            # MB_ICONERROR | MB_OK | MB_TOPMOST
            ctypes.windll.user32.MessageBoxW(0, message, title, 0x10 | 0x0 | 0x40000)
        except Exception:
            pass  # 弹窗本身不能再崩
    else:
        print(f"\n[FATAL] {title}\n{message}\n", file=sys.stderr)


def _write_crash_log(log_dir: str, exc_type, exc_val, exc_tb) -> str:
    """把崩溃堆栈写入独立 crash log 文件，避免主日志被截断

    Returns:
        crash log 文件的完整路径
    """
    import time
    os.makedirs(log_dir, exist_ok=True)
    crash_file = os.path.join(log_dir, f"crash_{time.strftime('%Y%m%d_%H%M%S')}.log")
    try:
        with open(crash_file, "w", encoding="utf-8") as f:
            f.write("LLM-Wiki CRASH REPORT\n")
            f.write("=" * 60 + "\n")
            f.write(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Frozen: {getattr(sys, 'frozen', False)}\n")
            f.write(f"Executable: {sys.executable}\n")
            f.write(f"CWD: {os.getcwd()}\n")
            f.write("=" * 60 + "\n\n")
            traceback.print_exception(exc_type, exc_val, exc_tb, file=f)
        return crash_file
    except Exception as e:
        return f"(failed to write crash log: {e})"


def _global_excepthook(exc_type, exc_val, exc_tb) -> None:
    """全局未处理异常捕获——兜底所有崩溃路径

    行为：
      1. 尝试写 crash log 到 %APPDATA%/LLM-Wiki/logs/
      2. 尝试写主日志 app.log
      3. 弹窗告知用户（打包模式）
    """
    # 先确定日志目录（path_resolver 本身可能也崩了，fallback 到 APPDATA）
    try:
        _, get_log_dir, _ = _get_path_resolver()
        log_dir = get_log_dir()
    except Exception:
        appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
        log_dir = os.path.join(appdata, "LLM-Wiki", "logs")

    crash_path = _write_crash_log(log_dir, exc_type, exc_val, exc_tb)

    # 也尝试写主日志
    try:
        logging.getLogger("launcher").critical(
            "未捕获的致命异常 | type=%s value=%s crash_log=%s",
            exc_type.__name__, exc_val, crash_path,
        )
    except Exception:
        pass

    # 弹窗（打包模式）
    tb_text = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
    message = (
        f"LLM-Wiki 遇到致命错误，无法继续运行。\n\n"
        f"错误类型: {exc_type.__name__}\n"
        f"错误信息: {exc_val}\n\n"
        f"崩溃日志已保存到:\n{crash_path}\n\n"
        f"请将此日志文件反馈给开发者。\n\n"
        f"--- 堆栈摘要 ---\n"
        f"{tb_text[-800:]}"  # 截断到最后 800 字符，避免弹窗过长
    )
    _show_error_dialog("LLM-Wiki 启动失败", message)


# 注册全局异常钩子——任何未捕获异常都走这里
sys.excepthook = _global_excepthook


def _threading_excepthook(args) -> None:
    """子线程异常捕获（uvicorn worker 线程中崩溃不会走 sys.excepthook）"""
    _global_excepthook(args.exc_type, args.exc_value, args.exc_traceback)


threading_excepthook_orig = getattr(threading, "excepthook", None)
try:
    threading.excepthook = _threading_excepthook
except (AttributeError, TypeError):
    pass


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
        return True
    except OSError:
        return False


def main():
    _, get_log_dir, is_frozen = _get_path_resolver()

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

    logger = logging.getLogger("launcher")

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

    app = _get_app()

    try:
        uvicorn.run(
            app,
            host=HOST,
            port=PORT,
            log_level="warning",
            reload=False,
            log_config=None,
        )
    except KeyboardInterrupt:
        logger.info("收到退出信号，优雅关闭...")
    except SystemExit:
        # uvicorn 内部 sys.exit() 正常传播，不拦截
        raise
    except Exception:
        # 让 sys.excepthook 统一处理（写 crash log + 弹窗）
        raise
    finally:
        logger.info("LLM-Wiki 已退出")


def _open_browser_and_exit():
    """已有实例运行时：打开浏览器访问已有实例后退出"""
    threading.Timer(0.5, lambda: webbrowser.open(f"http://{HOST}:{PORT}")).start()


def _auto_open_browser():
    """延迟 2 秒后自动打开浏览器"""
    timer = threading.Timer(2.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}"))
    timer.daemon = True
    timer.start()


if __name__ == "__main__":
    main()
