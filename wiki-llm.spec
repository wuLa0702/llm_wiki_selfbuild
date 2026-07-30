# -*- mode: python ; coding: utf-8 -*-
"""
LLM Wiki — PyInstaller 打包配置

打包为单文件 exe（--onefile），包含：
  - Python 运行时 + 所有依赖
  - src/ 源代码
  - wiki-ui-v2/dist/ 前端构建产物
  - static/ 静态资源

构建命令：
  pyinstaller wiki-llm.spec --clean

产物：
  dist/LLM-Wiki.exe  (~80-120 MB)
"""

import os
import sys
from pathlib import Path

# ── 项目根目录 ────────────────────────────────────────────────────────────
try:
    ROOT_DIR = Path(__file__).parent.absolute()
except NameError:
    # PyInstaller exec() 上下文不注入 __file__，fallback 到 CWD
    ROOT_DIR = Path.cwd()

# ── 前端构建产物（必须事先 npm run build） ────────────────────────────────
FRONTEND_DIST = ROOT_DIR / "wiki-ui-v2" / "dist"
if not FRONTEND_DIST.is_dir():
    print("[ERROR] 前端 dist 目录不存在，请先执行: cd wiki-ui-v2 && npm run build")
    sys.exit(1)

# ── 需要递归收集的数据文件 ────────────────────────────────────────────────
# PyInstaller 不会自动包含非 .py 文件，需显式声明
added_files = [
    # 前端静态文件（recursive 收集子目录）
    (str(FRONTEND_DIST / "assets"), "wiki-ui-v2/dist/assets"),
    (str(FRONTEND_DIST / "index.html"), "wiki-ui-v2/dist"),
    # 后端静态资源
    (str(ROOT_DIR / "static"), "static"),
]

# ── 隐藏导入（PyInstaller 静态分析可能遗漏的动态 import） ────────────────
hidden_imports = [
    # FastAPI 生态
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.loops.uvloop",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.middleware.debug",
    "uvicorn.middleware.proxy_headers",
    "uvicorn.middleware.wsgi",
    # LangChain
    "langchain_core",
    "langchain_openai",
    "langgraph",
    # YAML
    "yaml",
    # Template engines
    "jinja2",
    "jinja2.ext",
]

# ── Spec ──────────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT_DIR / "run.py")],          # 入口脚本
    pathex=[str(ROOT_DIR)],
    binaries=[],
    datas=added_files,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",           # GUI 框架（不用）
        "matplotlib",        # 绘图库（不用）
        "PIL",               # 图片处理（不用）
        "numpy",             # 科学计算（不用）
        "pandas",            # 数据处理（不用）
        "scipy",             # 科学计算（不用）
        "notebook",          # Jupyter（不用）
        "ipython",           # IPython（不用）
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="LLM-Wiki",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,               # UPX 压缩（减少 ~30% 体积）
    upx_exclude=[],
    runtime_tmpdir=None,     # 使用系统临时目录
    console=False,           # 无控制台窗口（Windows GUI 模式）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # TODO: 后续添加应用图标
)
