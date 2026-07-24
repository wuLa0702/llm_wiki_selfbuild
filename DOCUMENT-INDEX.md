# LLM Wiki 文档索引

> 生成日期：2026-07-23
> 用途：统一归纳所有文档，标注状态、过时程度和开发关注度

---

## 一、文档总览

| 目录 | 有效文档数 | 过时/历史 | 空占位 |
|:-----|:----------:|:---------:|:------:|
| `docs/` | 5 | 2 | 3 |
| `.specify/` | 6 | 10 | 1 |
| `.learnings/` | 3 | 0 | 0 |
| **合计** | **14** | **12** | **4** |

---

## 二、`docs/` — 项目运营文档（面向开发流程）

| # | 文件 | 状态 | 说明 | 关注度 |
|---|------|:----:|------|:------:|
| 1 | **`design-system.md`** | ✅ **活跃** | 前端设计系统（shadcn/ui CSS 变量 + 圆角/间距/字号/阴影），当前 SPA 完全遵循此规范 | 🔥 开发必读 |
| 2 | **`SOP.md`** | 🟡 **需更新** | 标准操作流程。文件限制写 200/350 行，但实际规则 `01-coding-style.md` 已调整为 750/1000。需同步 | 📋 下次改 |
| 3 | **`wiki-lint-analysis.md`** | 🟡 **半活跃** | LintPage 前后端差距分析。部分发现已被后续提交修复（健康评分/Index缺口已补），部分仍有效（语义 lint bug） | 👀 参考 |
| 4 | **`wiki-ui-feature-audit.md`** | 🟡 **半活跃** | 前端功能审计，列出所有页面和后端 API 的对应关系。部分页面后续大幅增强（Graph/Chat/Lint） | 👀 参考 |
| 5 | **`features/TEMPLATE.md`** | 🟡 **模板未用** | Feature spec 模板，存于 `docs/features/` 下，但从未创建过正式 feature 文档 | 📋 下次改 |
| 6 | `migration-audit.md` | 🔴 **历史文档** | HeroUI → shadcn/ui 迁移分析。迁移已全部完成，留存供参考 | ❌ |
| 7 | `decisions/.gitkeep` | ⚪ 空占位 | 决策记录目录，从未使用 | 🗑️ 可清理 |
| 8 | `discussions/.gitkeep` | ⚪ 空占位 | 讨论记录目录，从未使用 | 🗑️ 可清理 |
| 9 | `features/.gitkeep` | ⚪ 空占位 | Feature 规格目录，仅含 TEMPLATE | 🗑️ 可清理 |

---

## 三、`.specify/` — 设计规格文档（面向架构决策）

### 3.1 主文档

| # | 文件 | 状态 | 说明 | 关注度 |
|---|------|:----:|------|:------:|
| 1 | **`agent/chat-agent-final-plan.md`** | ✅ **🔥 当前活跃** | Chat Agent P1 最终实施方案。3 只读工具 + SSE 流式，2026-07-22 刚 finalized | 🔥 **最高优先级 — 下一开发任务** |
| 2 | **`references/knowledge-reference.md`** | ✅ **活跃** | 面试知识点手册，覆盖 Ingest/Query/Lint/图谱 等核心概念 | 📚 面试备战 |
| 3 | **`references/llm-wiki-commons.md`** | ✅ **活跃** | 7+ 个 LLM Wiki 框架共性设计模式提取，架构参考价值高 | 👀 参考 |
| 4 | **`interview-notes/phase2-cot-understanding.md`** | ✅ **活跃** | 两步 CoT 理解笔记，含面试话术 | 📚 面试备战 |

### 3.2 部分过时（需更新或确认）

| # | 文件 | 状态 | 过时原因 | 关注度 |
|---|------|:----:|----------|:------:|
| 5 | `references/architecture.md` | 🟡 **偏旧** | 项目结构图缺少 `wiki-ui-v2/`、`sandbox/` 等目录；无前端的 Phase 1 设计已过时。核心三层架构仍有效 | 📋 考虑更新 |
| 6 | `references/tech-stack.md` | 🔴 **大幅过时** | 前端描述 Jinja2+htmx，实际已是 React SPA + shadcn/ui + Vite。后端描述基本准确 | 📋 需重写前端部分 |
| 7 | `references/ui-behavior-guide.md` | 🔴 **大幅过时** | 旧 Jinja2 模板体系规范（三区模型、block 继承、htmx 导航），当前 React SPA 完全不适用 | 📋 需重写或废弃 |
| 8 | `roadmap.md` | 🔴 **严重过时** | Phase 完成百分比严重不准确：Phase 5(BM25+混合搜索)已实现80%，Phase 6(React SPA)已基本完成。Phase 路线图需要整体重写 | 📋 **高优先级—路线图需重建** |
| 9 | `roadmaps/phase6-design.md` | 🔴 **过时** | 描述 Jinja2 + htmx 的 UI 美化方案，但实际走的是 React SPA + shadcn/ui 路线 | 📋 考虑废弃 |
| 10 | `agent/development-plan.md` | 🟡 **偏旧** | 规划了 sandbox/ → src/agent/ 的演进路径，但实际方案已跳过 sandbox 直接集成到 src/agent/ | 👀 参考 |
| 11 | `agent/phase1-implementation-plan.md` | 🔴 **被取代** | sandbox 实验脚本的详细实现计划，被 `chat-agent-final-plan.md` 完全取代 | ❌ 可归档 |
| 12 | `ui-design.md` | 🟡 **偏旧** | React + HeroUI 时代的设计文档。当前 UI 已迁移到 shadcn/ui，但布局和路由设计仍有参考价值 | 👀 参考 |

### 3.3 历史文档（已完成阶段）

| # | 文件 | 状态 | 对应 Git 证据 |
|---|------|:----:|--------------|
| 13 | `roadmaps/phase1.md` | ✅ **已完成** | `6cce6cf` 之前的所有早期提交 |
| 14 | `roadmaps/phase2.md` | ✅ **已完成** | Phase 2 功能在 `e2081ea` ~ `bb5cc30` 等提交中完成 |
| 15 | `roadmaps/phase3.md` | ✅ **已完成**(大部分) | Query/图解析/Lint/Watcher 等提交覆盖全部功能 |
| 16 | `roadmaps/phase3-selfcheck.md` | ✅ **已完成** | 自检修正项（WikiGraph + 静态 Lint）均已实现 |
| 17 | `roadmaps/phase4.md` | ✅ **已完成**(大部分) | 四信号图谱/MCP/Louvain/队列 等提交覆盖 |
| 18 | `roadmaps/phase5.md` | 🟡 **部分完成** | BM25 搜索已实现(`6cce6cf`)，向量搜索 + i18n 待办 |
| 19 | `roadmaps/phase6.5-sources-settings.md` | ✅ **已完成**(大部分) | 资料源/设置页重构已在 React SPA 中完成 |
| 20 | `frontend-migration.md` | 🔴 **已完成** | htmx→React+HeroUI 迁移完成；后又从 HeroUI → shadcn/ui |

---

## 四、`.learnings/` — 学习笔记

| # | 文件 | 状态 | 说明 |
|---|------|:----:|------|
| 1 | `README.md` | ✅ 活跃 | .learnings 目录说明 |
| 2 | `git-rebase-mass-squash.md` | ✅ 活跃 | Git 批量 rebase 技巧 |
| 3 | `interview-notes.md` | ✅ 活跃 | 面试复盘笔记 |

---

## 五、功能状态全景图（基于 Git Log）

| 功能域 | 状态 | 最后关键提交 | 说明 |
|:-------|:----:|:------------|:------|
| **Ingest 闭环** | ✅ **完成** | `f13b9f1` | 两步 CoT + SHA256 缓存 + 隐私过滤 + force 重 ingest |
| **Query 查询** | ✅ **完成** | `d0ba35c` | 图扩展查询 + BM25 混合搜索 |
| **知识图谱** | ✅ **完成** | `f92346b` | 四信号模型 + Louvain 社区 + 洞察 + 3视图 + 缓存 |
| **MCP Server** | ✅ **完成** | `d352f92` | Agent 配置 + MCP 集成 |
| **Lint 检查** | ✅ **完成** | `d87c821` | 静态+语义 lint + 健康评分 + 自动修复 |
| **Source 监听** | ✅ **完成** | `d82faae` | Watcher + 白名单/黑名单/DB 配置 |
| **上传/导入** | ✅ **完成** | `5b3727c` | 文件夹导入 + 进度轮询 + 队列可视化 |
| **BM25 搜索** | ✅ **完成** | `0bb1e47` | 章节级多命中 + 分数归一化 + 翻页 |
| **混合搜索 RRF** | ✅ **完成** | `d0ba35c` | BM25 + 向量语义 RRF 融合 |
| **React SPA 前端** | ✅ **基本完成** | `cb64dec` | 9 页面 + shadcn/ui + 空状态 + 测试框架 |
| **Chat Agent P1** | ⬜ **待开发** | — | 3 只读工具 + SSE 流式，方案已 finalized |
| **向量搜索** | 🟡 **部分完成** | `d0ba35c` | 基础向量索引存在，LanceDB 集成待加强 |
| **i18n 国际化** | ⬜ **待办** | — | 配置文件驱动，未启动 |
| **PPTX/XLSX 解析** | ⬜ **待办** | — | 依赖库未安装 |
| **Agent 对话记忆** | ⬜ **待办** | — | P2 计划中 |
| **打包发布** | ⬜ **待办** | — | PyInstaller 单 exe 分发 |

---

## 六、未来开发关注文档

以下文档是后续开发中需要重点关注的：

| 优先级 | 文档 | 原因 |
|:------:|:-----|:------|
| 🔥 P0 | **`agent/chat-agent-final-plan.md`** | 下一开发任务——Chat Agent P1 实施方案 |
| 🔥 P0 | **`design-system.md`** | 所有前端开发的设计规范依据 |
| 📋 P1 | **重写 `roadmap.md`** | 当前版本严重过时，Phase 5/6/7 进度不准确 |
| 📋 P1 | **更新 `references/tech-stack.md`** | 前端技术栈描述过时（Jinja2→React SPA） |
| 📋 P2 | **更新 `references/ui-behavior-guide.md`** | 或废弃，创建 React SPA 版 UI 规范 |
| 📋 P2 | **更新 `references/architecture.md`** | 补充新目录结构（wiki-ui-v2/, sandbox/） |
| 📋 P2 | **整理 `docs/features/`** | 要么用 TEMPLATE 开始写 feature 文档，要么清理目录 |
| 📋 P3 | **`docs/SOP.md` 同步** | 文件行数约束与 `01-coding-style.md` 同步 |

---

## 七、建议清理项

| 文件 | 建议操作 | 理由 |
|:-----|:--------|:------|
| `docs/decisions/.gitkeep` | 🗑️ **删除** | 空占位，从未使用 |
| `docs/discussions/.gitkeep` | 🗑️ **删除** | 空占位，从未使用 |
| `docs/features/.gitkeep` | 🗑️ **删除** | 空占位，仅含模板 |
| `migration-audit.md` | 📦 归档或删除 | 迁移已完成 |
| `frontend-migration.md` | 📦 归档或删除 | 迁移已完成 |
| `agent/phase1-implementation-plan.md` | 📦 归档到 `agent/archive/` | 被 chat-agent-final-plan.md 取代 |
| `roadmaps/phase1.md` | 📦 可归档 | 历史阶段 |
| `roadmaps/phase2.md` | 📦 可归档 | 历史阶段 |
| `roadmaps/phase3.md` | 📦 可归档 | 历史阶段（自检报告可保留参考） |
| `roadmaps/phase4.md` | 📦 可归档 | 历史阶段（大部分已完成） |

---

*文档索引自动生成于 2026-07-23。建议每次 Phase 结束后更新此索引。*
