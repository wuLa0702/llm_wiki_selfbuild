# 现有前端功能审计

> 用途：新前端（wiki-ui-v2/）实现时对照，确保不丢功能
> 生成时间：2026-07-19

---

## 一、页面清单

| 路由 | 组件 | 文件 | 功能简述 |
|------|------|------|---------|
| `/wiki/home` | `HomePage` | `pages/HomePage.tsx` | 首页/原始资料 |
| `/wiki` | `WikiPage` | `pages/WikiPage.tsx` | 知识库浏览（文件树 + 文档详情） |
| `/chat` | `ChatPage` | `pages/ChatPage.tsx` | AI 对话 |
| `/search` | `SearchPage` | `pages/SearchPage.tsx` | 混合搜索 |
| `/graph` | `GraphPage` | `pages/GraphPage.tsx` | 知识图谱 |
| `/wiki/audit` | `AuditPage` | `pages/AuditPage.tsx` | Wiki 断链检查 |
| `/settings/:tab` | `SettingsPage` | `pages/SettingsPage.tsx` | 设置页 |
| `/test-card` | `TestCardPage` | `pages/TestCardPage.tsx` | 组件测试页（**迁移后删除**） |
| (独立路由) | `QueryPage` | `pages/QueryPage.tsx` | 问答页面（当前未在路由表中注册） |
| (独立路由) | `HealthPage` | `pages/HealthPage.tsx` | 健康检查（当前未在路由表中注册） |
| (独立路由) | `LintPage` | `pages/LintPage.tsx` | Lint 检查（另一个版本） |
| (独立路由) | `FilePage` | `pages/FilePage.tsx` | 文件浏览（另一个版本） |
| (独立路由) | `SourcesPage` | `pages/SourcesPage.tsx` | 原始资料（功能最全版本） |

> **说明**：有多组功能重复的页面（SourcesPage/FilePage/HomePage 都做原始资料浏览，LintPage/AuditPage 都做检查）。新前端只需保留每个功能的最佳版本。

---

## 二、页面详细功能

### 2.1 首页 / 原始资料（HomePage + SourcesContent）

| 功能 | 实现方式 |
|------|---------|
| 加载原始资料文件树 | `GET /v1/sources/tree` |
| 显示文件列表（平铺，所有文件拍平） | 递归 walk tree → 列表渲染 |
| 选中文件预览内容 | `GET /v1/file-content?path=xxx` |
| Markdown 渲染（.md 文件） | `renderMarkdown()` + dangerouslySetInnerHTML |
| 普通文本文件预览（非 .md） | `<pre>` 标签显示 |
| 删除文件 | `DELETE /v1/sources/delete?path=xxx`（确认弹窗） |
| 刷新文件列表 | 按钮 + `loadTree()` |
| 上传单个/多个文件 | `<input type="file" multiple>` → `POST /v1/ingest/upload` |
| 上传文件夹 | `<input webkitdirectory>` → `POST /v1/ingest/upload` |
| 提取文件到 Wiki | `POST /v1/sources/extract-to-wiki` |
| 删除文件夹 | `DELETE /v1/sources/folder/{path}` |
| 导入队列轮询 | `GET /v1/ingest/queue/recent?limit=10`，每 5s |
| 文件数量统计 | 底部显示 "N 个资料" |

### 2.2 知识库浏览（WikiPage + MidPanel + WikiContent + MarkdownRenderer）

| 功能 | 实现方式 |
|------|---------|
| 加载 Wiki/raw 文件树 | `GET /v1/file-tree` |
| 目录树展开/收起 | 状态记录展开路径，▶ 旋转动画 |
| 文件/目录图标 | 📁 📄 emoji |
| Wiki/raw 标签切换 | tab 切换 wiki | raw |
| 自动展开到当前文件 | activePath 变化时自动展开路径 |
| 选中文件加载详情 | `GET /v1/pages/{path}` |
| 降级方案（API 404） | fallback 到 `GET /v1/file-content?path=xxx` |
| 页面元数据显示 | 类型标签（实体/概念/引用源）、标题、创建时间、标签 |
| 来源溯源显示 | "📂 来源溯源" + Tooltip 展示完整路径 |
| 正向引用链接 | "🔗 正向引用 (N)" → `[[wikilinks]]` 列表 |
| 反向引用链接 | "🔙 反向引用 (N)" → `[[backlinks]]` 列表 |
| 链接可点击跳转 | onNavigate 回调 → 切换到目标页面 |
| Markdown 渲染 | `MarkdownRenderer`（marked 解析，支持 wikilinks） |
| 行内编辑 | textarea 替换内容区，可编辑保存 |
| 加载状态 | "⏳ 加载中..." |
| 空状态 | 📂 + "Select a file to preview" |
| 错误状态 | ❌ 错误信息 + 返回按钮 |
| Markdown wikilinks 解析 | `[[path]]` 和 `[[path\|label]]` 两种格式 |
| Markdown 全元素支持 | heading/h1-h6, paragraph, code block, list, table, blockquote, hr, html, image, link |

### 2.3 AI 对话（ChatPage）

| 功能 | 实现方式 |
|------|---------|
| 会话列表（左侧） | 260px 侧栏，可折叠 |
| 新建对话 | 按钮 → 创建空会话 |
| 消息发送 | TextArea 输入 → Enter 发送 |
| 用户消息气泡 | 右对齐，Card primary 色 |
| AI 回复气泡 | 左对齐，Card bordered |
| 模拟加载态 | setTimeout 模拟 1.5s 回复 |
| 消息复制 | Copy 按钮 |
| 重新生成 | Regenerate 按钮 |
| 保存到 Wiki | Save to Wiki 按钮（功能桩） |
| 模式选择 | ToggleButtonGroup: 快速/标准/深度/本地优先 |
| 对话历史持久化 | localStorage 存储 |
| 会话标题自动生成 | 取第一条消息前 30 字符 |
| 会话日期显示 | `toLocaleDateString` |
| 技能数显示 | "✓ N skill(s) available" Chip |
| 空状态 | EmptyState 组件 + "开始对话" |
| 附加功能按钮 | 添加图片/网页搜索/AnyTXT 搜索/Skills |
| 消息数量统计 | "N 条消息" |

### 2.4 搜索（SearchPage）

| 功能 | 实现方式 |
|------|---------|
| 搜索输入框 | Enter 触发搜索 |
| 混合搜索 | `POST /v1/search` with method: 'hybrid', k: 20 |
| 搜索结果展示 | 标题 + 路径 + 摘要 snippet |
| 空状态 | 🔍 + "Press Enter to search" |
| 无结果处理 | 空列表 → 无结果显示 |

### 2.5 知识图谱（GraphPage）

| 功能 | 实现方式 |
|------|---------|
| 加载图谱数据 | `GET /v1/graph` |
| 节点/链接统计 | "N nodes / N links" |
| Canvas 渲染 | `<canvas>` 元素（当前为空，无实际渲染逻辑） |
| 操作按钮 | Filter / Reset / View / Community（功能桩） |
| 加载状态 | "加载中..." |
| 空状态 | 🕸️ + "没有可见节点" |

### 2.6 Wiki 检查 / Audit（AuditPage）

| 功能 | 实现方式 |
|------|---------|
| 执行检查 | `GET /v1/lint?semantic=false` |
| 断链列表 | source → target 显示 |
| 批量选择 | checkbox + 全选 |
| 修复选中项 | 按钮（功能桩） |
| 移入待审阅 | 按钮（功能桩） |
| 忽略选中项 | 按钮（功能桩） |
| 打开断链源文件 | 按钮 → 可跳转 |
| 单个修复 | 按钮（功能桩） |
| 警告计数 | "警告 (N)" |
| 空状态 | ✅ + "未发现断链" |

### 2.7 Lint 检查（LintPage — 功能重复，更完整版本）

| 功能 | 实现方式 |
|------|---------|
| 执行检查 | `GET /v1/lint?semantic=false` |
| 语义检查 | `GET /v1/lint?semantic=true`（调用 LLM 做深度检查） |
| 检查结果摘要 | summary 字段展示 |
| 断链列表 | source → target |
| 孤立页面列表 | 无入链/无出链的页面 |
| 加载/检查中状态 | 按钮 disabled + "检查中..." |
| Toast 通知 | 操作结果反馈 |

### 2.8 设置（SettingsPage）

| 功能 | 实现方式 |
|------|---------|
| 标签页导航 | 通用 / 界面 / LLM 模型 / 向量嵌入 / 网络 |
| 界面语言切换 | 中文 / English |
| 主题切换 | 浅色 / 深色 / 跟随系统 |
| 界面缩放 | − / 输入框 / +，范围 50%-200% |
| 保存设置 | localStorage 持久化 `ui_lang`, `ui_theme`, `ui_zoom` |
| LLM 模型列表 | DeepSeek V4 Flash / Claude Sonnet 4.6 / GPT-4o（功能桩） |
| 模型启停开关 | toggle 开关（功能桩） |

### 2.9 问答（QueryPage — 当前独立页面，未注册路由）

| 功能 | 实现方式 |
|------|---------|
| 问题输入框 | Enter 触发查询 |
| 发送查询 | `POST /v1/query` |
| 答案展示 | 纯文本 + 置信度标签（高/中/低） |
| 来源展示 | 引用页面路径列表 |
| 加载状态 | "查询中..." |
| 置信度色标 | 高绿/中黄/低红 |

### 2.10 健康检查（HealthPage — 当前独立页面，未注册路由）

| 功能 | 实现方式 |
|------|---------|
| 服务状态检测 | `GET /health` |
| 状态显示 | 绿点 "服务正常" / 红点 "服务异常" |
| 详情展示 | JSON 格式化输出 |

---

## 三、公共组件清单

| 组件 | 文件 | 功能 |
|------|------|------|
| `Sidebar` | `components/Sidebar.tsx` | 左侧导航菜单（emoji 图标 + 路由链接） |
| `MidPanel` | `components/MidPanel.tsx` | Wiki/raw 文件树 + 导入队列抽屉（功能最多的侧栏） |
| `TreePanel` | `components/TreePanel.tsx` | 知识库/文件双标签 + 搜索过滤 + 分类分组 |
| `WikiContent` | `components/WikiContent.tsx` | Wiki 文档详情（元信息卡片 + Markdown 正文） |
| `MarkdownRenderer` | `components/MarkdownRenderer.tsx` | Markdown 渲染引擎（支持 wikilinks） |
| `SourcesContent` | `components/SourcesContent.tsx` | 原始资料列表 + 预览 |
| `Toast` | `components/Toast.tsx` | 轻量通知（success/error/info） |
| `TaskQueue` | `components/TaskQueue.tsx` | 导入队列状态面板（轮询 + 操作按钮） |

---

## 四、工具/基础设施

| 文件 | 功能 |
|------|------|
| `utils/markdown.ts` | `stripFrontmatter()` 剥离 YAML 头部 / `renderMarkdown()` 渲染含 wikilinks 的 Markdown / `escapeHtml()` |
| `api/client.ts` | 封装 ky HTTP 客户端：`fetchJson`, `postJson`, `deleteJson` |
| `hooks/useApi.ts` | `useApi<T>()` 通用数据请求 hook / `usePolling<T>()` 轮询 hook |
| `index.css` | Tailwind v4 入口 + HeroUI 样式引入 + 自定义 Markdown 样式 |
| `typography.css` | 排版样式 |

---

## 五、后端 API 依赖（新前端需对接的接口）

| 方法 | 路径 | 用途 | 调用方 |
|------|------|------|--------|
| GET | `/health` | 健康检查 | HealthPage |
| GET | `/v1/file-tree` | 获取文件树（wiki + raw） | MidPanel |
| GET | `/v1/pages` | 获取所有页面列表 | TreePanel |
| GET | `/v1/pages/{path}` | 获取单页详情（含元数据） | WikiContent |
| GET | `/v1/file-content?path=xxx` | 获取原始文件内容 | SourcesContent, FilePage |
| POST | `/v1/search` | 混合搜索 | SearchPage |
| POST | `/v1/query` | Wiki 问答 | QueryPage |
| GET | `/v1/lint?semantic=bool` | Lint 检查 | AuditPage, LintPage |
| GET | `/v1/graph` | 图谱数据 | GraphPage |
| POST | `/v1/ingest/upload` | 上传文件 | HomePage, SourcesPage |
| GET | `/v1/ingest/queue/recent?limit=N` | 队列近期任务 | SourcesPage, MidPanel |
| GET | `/v1/ingest/queue/status` | 队列统计 | TaskQueue |
| POST | `/v1/ingest/queue/retry/{jobId}` | 重试任务 | SourcesPage, MidPanel |
| DELETE | `/v1/ingest/queue/{jobId}` | 删除任务 | SourcesPage, MidPanel |
| DELETE | `/v1/ingest/queue/all` | 清空所有记录 | MidPanel |
| DELETE | `/v1/ingest/queue/failed` | 清空失败记录 | MidPanel |
| GET | `/v1/sources/tree` | 原始资料文件树 | SourcesContent |
| DELETE | `/v1/sources/delete?path=xxx` | 删除原始文件 | SourcesContent |
| DELETE | `/v1/sources/folder/{path}` | 删除文件夹 | SourcesContent |
| POST | `/v1/sources/extract-to-wiki` | 提取文件到 Wiki | SourcesContent |

---

## 六、路由对照（新前端需要实现的路由）

| 路由 | 功能 | 优先级 |
|------|------|:------:|
| `/` 或 `/home` | 首页/仪表盘（统计 + 最近更新） | P1 |
| `/wiki` | 知识库浏览（文件树 + 文档详情） | P1 |
| `/chat` | AI 对话 | P1 |
| `/search` | 混合搜索 | P1 |
| `/graph` | 知识图谱 | P1 |
| `/settings/:tab` | 设置页 | P1 |
| `/sources` | 原始资料管理（上传/删除/预览） | P1 |
| `/lint` 或 `/audit` | Wiki 健康检查 | P2 |
| `/query` | 问答页面 | P2 |
| `/health` | 健康检查 | P3 |
