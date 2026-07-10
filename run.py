"""
LLM Wiki — 桌面应用入口（内嵌浏览器窗口）

双击运行即弹出窗口，不显示命令行（打包模式下）。
开发模式: python run.py --dev    # 显示命令行+浏览器
"""
import os
import sys
import threading
import argparse
import socket

# 立即隐藏控制台（打包模式下）
if getattr(sys, "frozen", False):
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)
    except Exception:
        pass


def find_free_port(start: int = 8765, max_attempts: int = 20) -> int:
    """从 start 开始找第一个空闲端口"""
    for port in range(start, start + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"在 {start}-{start+max_attempts-1} 范围内未找到空闲端口")


def start_server(host: str, port: int):
    """在后台线程启动 uvicorn"""
    import uvicorn
    uvicorn.run("src.main:app", host=host, port=port, reload=False, log_level="warning")


def main():
    parser = argparse.ArgumentParser(description="LLM Wiki Desktop")
    parser.add_argument("--dev", action="store_true", help="开发模式（显示命令行+浏览器）")
    args = parser.parse_args()

    # 路径处理
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(sys.executable)
        os.chdir(exe_dir)
        internal_dir = os.path.join(exe_dir, "_internal")
        if internal_dir not in sys.path:
            sys.path.insert(0, internal_dir)
        os.environ["LLM_WIKI_RESOURCE_DIR"] = internal_dir
    else:
        os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # 确保数据目录
    os.makedirs("wiki", exist_ok=True)
    os.makedirs("raw", exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    # 自动找空闲端口
    host = "127.0.0.1"
    port = find_free_port()
    url = f"http://{host}:{port}/wiki"
    print(f">>> LLM Wiki 启动中 -> {url}")

    # 后台启动 FastAPI 服务器
    server_thread = threading.Thread(target=start_server, args=(host, port), daemon=True)
    server_thread.start()

    # 等待服务器就绪
    import urllib.request
    import time
    for i in range(30):
        try:
            urllib.request.urlopen(f"http://{host}:{port}/wiki", timeout=1)
            break
        except Exception:
            time.sleep(0.5)

    if args.dev:
        # 开发模式：用浏览器打开
        import webbrowser
        webbrowser.open(url)
        print(f"浏览器已打开: {url}")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    else:
        # 桌面模式：弹出 webview 窗口
        try:
            import webview
            window = webview.create_window(
                title="LLM Wiki",
                url=url,
                width=1200,
                height=800,
                min_size=(800, 600),
                resizable=True,
                text_select=True,
            )
            webview.start(gui=None, debug=False)
        except ImportError:
            print("[WARN] pywebview 未安装，回退到浏览器模式")
            import webbrowser
            webbrowser.open(url)


if __name__ == "__main__":
    main()
