# Claude Code 配置说明

## MCP 服务器

本项目可用的 MCP 服务器（基于全局用户配置 `~/.claude.json`）：

| 服务器 | 类型 | 用途 | 配置源 |
|--------|------|------|--------|
| `dida365` | HTTP | 滴答清单任务管理：增删改查、过滤、评论、习惯、专注记录 | 全局 |
| `fetch` | stdio | URL 页面抓取与内容提取 | 全局 |
| `github` | stdio | GitHub API 操作：Issue/PR/分支/文件/搜索 | 全局 |
| `memory` | stdio | 知识图谱记忆：实体/关系/观测持久化 | 全局 |
| `node_repl` | stdio | Node.js 交互式执行环境，支持 Playwright 浏览器自动化 | 全局 |
| `playwright` | stdio | 浏览器自动化：页面导航、点击、截图、表单填写 | 全局 |
| `time` | stdio | 时间查询与时区转换 | 全局 |
| `findskills` | stdio | 技能市场搜索与安装 | 全局 |
| `filesystem` | stdio | 文件系统操作（限 `D:\gtiHub\llm_wiki_selfbuild`） | 全局 |
| `firecrawl` | stdio | 网页爬取、搜索、结构化内容提取（**需 API Key**） | 全局 |
| `context7` | stdio | 实时库文档查询，消除幻觉 API | 全局 |
| `git-mcp` | stdio | 本地 Git 操作：diff/stage/commit/stash/log/blame + 标准化 Commit 信息生成 + Lint 联动 | 项目级 |

> 注：大部分 MCP 服务器在 `~/.claude.json` 的 `mcpServers` 中统一配置，全项目共享。
> `git-mcp` 是项目级配置（限定本仓库），在 `.claude/settings.json` 中定义。

### ⚠️ 新增 MCP 说明

| 服务器 | 注意事项 |
|--------|---------|
| **findskills** | 现已添加至全局配置。使用 `/find-skills` 或 `find skills about ...` 即可调用 |
| **filesystem** | 限定为本项目目录，可读可写。**注意**：它绕过项目自定义的 `ReadTool`/`WriteTool` 权限校验（`raw/` 只读策略），使用时需自行注意不要误改 `raw/` |
| **firecrawl** | 依赖 API Key，免费注册 [firecrawl.dev](https://www.firecrawl.dev) 获取。未配 Key 时基础功能受限 |
| **context7** | 免配置，`npx` 模式开箱即用。写代码时自动查询库的最新文档 |
| **git-mcp** | 项目级配置，只作用于本仓库。自动读 diff 生成标准化 commit 信息（feat/fix/docs/refactor），支持 lint 联动 |

---

## 本项目最简 MCP 方案

LLM Wiki 是**纯 Python 后端项目**（FastAPI + LangChain + SQLite + Markdown），不同阶段需要的 MCP 不同：

### Phase 1（MVP）— 必要
只需要一个就够：

```
fetch    → 写代码时查官方文档、技术博客
```

你现有的 `fetch` 已经覆盖了 Phase 1 的信息获取需求。代码不依赖任何 MCP 运行。

### Phase 2（Ingest / Query / Lint）— 推荐按需加

| MCP | 做 Ingest 时 | 做 Query 时 | 做 Lint 时 |
|-----|-------------|-------------|-----------|
| **context7** | 查 LangChain/FastAPI 最新 API | — | — |
| **firecrawl** | 🔥 抓取网页作为原始素材 | 搜索外部知识补充回答 | — |
| **filesystem** | 替代手写文件工具 | — | 批量扫描 Wiki |

### Phase 3（多 Agent）— 进阶
```
memory   → Agent 间共享长期记忆
node_repl → 沙箱执行验证代码
```

### 一句话总结

> **本项目运行本身零 MCP 依赖**。MCP 是辅助 Claude 编码效率的工具，不是项目运行时依赖。
>
> Phase 1 你现有的 7 个 MCP 已经足够。
> Phase 2 做 Ingest 时，**firecrawl** 抓素材最实用。
> **context7** 任何时候写代码都有帮助。

---

## 规则文件

| 文件 | 用途 |
|------|------|
| `rules/00-security.md` | 安全规则：路径校验、穿越防御、LLM 输出验证 |
| `rules/01-coding-style.md` | 编码风格：命名、类型注解、文档、导入顺序 |
| `rules/10-api.md` | API 规范：路由、Pydantic 模型、错误格式 |
| `rules/11-frontend.md` | 前端规范（预留 Phase 2/3） |
| `rules/12-backend.md` | 后端规范：分层架构、工具模式、LLM/DB 适配 |
| `rules/20-testing.md` | 测试规范：结构、Mock 策略、边界覆盖 |

## 环境变量

参见项目根目录 `.env` 文件（**不提交 Git**，已在 `.gitignore` 中忽略）。
