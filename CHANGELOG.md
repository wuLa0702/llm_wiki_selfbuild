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

### 技术债务
- `wiki.db` 路径仍有多处硬编码，后续应迁移到 path_resolver
- PyInstaller 构建签名和图标待完成
- 首次运行引导页面待添加
