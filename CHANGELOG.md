# Changelog

## [Unreleased] — v0.1.0 打包改造

### 新增
- `src/utils/path_resolver.py` — 统一路径解析入口，支持 `%APPDATA%/LLM-Wiki/` 持久化
- `src/utils/config_manager.py` — config.yaml 配置管理，支持 API Key 持久化
- `run.py` — 应用启动入口，支持 PyInstaller 打包、单实例互斥锁、自动开浏览器
- `wiki-llm.spec` — PyInstaller 打包配置（--onefile, UPX 压缩）
- `scripts/build-exe.bat` — 一键构建脚本（npm build → test → pyinstaller）
- `docs/release-guide.md` — Release 发布指南

### 变更
- `agent_persistence.db` → `%APPDATA%/LLM-Wiki/agent_persistence.db`（对话记忆跨版本保留）
- `safe_path()` 自动解析 `wiki`/`raw` 别名到 `%APPDATA%` 路径
- `main.py` 静态资源和前端 dist 路径改为 path_resolver 解析
- `scripts/dev-restart.bat` → 无弹窗后台运行、UTF-8 编码日志、/health 轮询等待

### 修复
- 测试 `test_read_page` 系列改用 monkeypatch 覆盖路径，兼容 path_resolver
- `.gitignore` 添加 `.obsidian/` 全局忽略
- 开发模式路径回退到 CWD（而非 %APPDATA%），修复 health 端点 `total_pages` 永远为 0
- PyInstaller spec 中 `__file__` NameError（exec() 上下文无 `__file__`）
- `uvicorn.logging.DefaultFormatter` 在 `console=False` 时 `sys.stdout=None` 崩溃
- EXE 打包后路径全部指向 `%APPDATA%/LLM-Wiki/`，不再意外读写 CWD
- Agent 同步 LLM 调用（`with_structured_output.invoke`）移到 `asyncio.to_thread`，防止阻塞事件循环导致进程崩溃

### 已知问题（打包相关 — 已全部关闭）
- ~~`build-exe.bat` 行 67 的 Size 显示直接输出算式而非计算结果~~ ✅ 修复于 `4a85fdb`
- ~~`build-exe.bat` 行 71 的 `>/dev/null` 在 Windows 中无效，应改为 `>nul`~~ ✅ 修复于 `4a85fdb`
- ~~`wiki.spec`（轻量版）落后于代码库~~ ✅ 已弃用并归档至 `docs/legacy/`，`wiki-llm.spec` 为唯一构建入口

### 技术债务
- `wiki.db` 路径已通过 `src/utils/path_resolver.py` 集中管理，各模块使用 `get_db_path()` 统一解析
- PyInstaller 构建签名和图标待完成（功能增强，非 bug）
- 首次运行引导页面待添加（功能增强，非 bug）
