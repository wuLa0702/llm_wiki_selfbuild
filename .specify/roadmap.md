# LLM Wiki 完整开发路线图

> **目标**：从 0 到 1 构建一个具备面试竞争力的 LLM Wiki 系统。
>
> **技术栈**：Python 3.11+ / FastAPI / LangChain / SQLite / Markdown
>
> **差异化定位**：Python 全栈 + 独立 API 服务 + 完整安全模型
>
> 📂 **本目录文件关系**：
> - `roadmap.md`（本文件）— 全局路线图：阶段目标 + 功能概览 + 面试要点 + 开发约定
> - `roadmap-phase1.md` — Phase 1 详细任务分解（日常开发的 checklist）
> - `001-整体架构设计.md` — 项目自身的技术架构设计
> - `llm-wiki-commons.md` — 外部参考：7+ 个框架的共性设计模式
> - `knowledge-reference.md` — 知识点手册：概念解释 + 面试话术 + 参考链接
> - `interview-notes/` — 每阶段结束后的面试复盘记录

---

## 对标项目的发展阶段参考

分析 nashsu/llm_wiki（12,500+ stars）和 cobusgreyling/llm-wiki（Python 实现）的发展节奏：

| 对标版本 | 功能范围 | 开发周期参考 |
|----------|---------|-------------|
| **v0.1** | 基础 CLI + 三层架构 + 单步 Ingest | ~2-4 周 |
| **v0.2** | 两步 CoT 摄入 + SHA256 缓存 + index.md/log.md + 元数据 | ~2-3 周 |
| **v0.3** | 知识图谱（wikilinks 解析+可视化）+ Query 查询 + Lint 检查 | ~3-4 周 |
| **v0.4** | 搜索增强 + MCP Server + 向量搜索 + API 完善 | ~3-4 周 |
| **v0.5** | Review 系统 + Deep Research + 多格式支持 + UI 完善 | ~4-6 周 |

> nashsu/llm_wiki 从 v0.1 到 v0.5 大约用了 3 个月（2026年4月→6月），每日高频迭代。

---

## 我们的开发阶段

### 阶段总览

```
Phase 1          ████████████████████  100% ✅
Phase 2（当前）    ████░░░░░░░░░░░░░░░░   20%  ← 你在的位置
Phase 3          ░░░░░░░░░░░░░░░░░░░░   0%  增强摄入 + Query 查询
Phase 4          ░░░░░░░░░░░░░░░░░░░░   0%  知识图谱 + Lint 检查
Phase 5          ░░░░░░░░░░░░░░░░░░░░   0%  搜索 + MCP + 面试打磨

面试就绪线 ──────────────────────────── Phase 4.5 即可达到
```

---

## Phase 1：基础 Ingest 闭环 ✅

> **状态**：✅ 已完成
> **对标**：nashsu v0.1 / cobusgreyling v0.1
> **详细任务清单**：[roadmap-phase1.md](roadmap-phase1.md)

### 核心目标

LLM 能读取 raw/ 下的源文件，编译后写入 wiki/，并记录元数据到 SQLite。通过 `POST /v1/ingest` API 调用，端到端跑通。

### 已完成 ✅

- LLMAdapter — DeepSeek 调用 + Provider 抽象
- ReadTool — raw/ 只读 + 路径安全
- WriteTool — wiki/ 写入 + 路径安全
- WikiRepository — SQLite 元数据存储
- 日志系统 + 安全规则

### 待完成 📋

- WikiCompiler.ingest() 核心编排逻辑
- POST /v1/ingest API 端点
- 集成测试 + pytest 全部通过

> 详见 [roadmap-phase1.md](roadmap-phase1.md) 了解每个任务的依赖关系和具体文件路径。

---

## Phase 2：增强摄入 + 元数据完善

> **状态**：🟡 进行中
> **对标**：nashsu v0.2 / cobusgreyling v0.2
> **详细任务清单**：[roadmap-phase2.md](roadmap-phase2.md)（日常开发参考，含依赖链和验证命令）

### 目标

把"能跑通"升级为"能生产用"——加入缓存、元数据、质量信号。

### 功能清单

| 功能 | 文件 | 说明 |
|------|------|------|
| **SHA256 增量缓存** | `src/core/wiki_compiler.py` | 源文件内容哈希 → 未变则跳过，省 tokens |
| **两步 CoT 摄入** | `src/core/wiki_compiler.py` | Step 1: LLM 分析 → Step 2: LLM 生成 |
| **index.md 自动维护** | `src/core/wiki_compiler.py` | 每次摄入后更新全局目录 |
| **overview.md 自动更新** | `src/core/wiki_compiler.py` | 全局综述页面 |
| **sources/ 来源摘要页** | `src/tools/write_tool.py` | 每个源文件对应一个摘要页 |
| **Purpose.md** | 项目根目录 | 知识库目标声明（LLM 每次读） |
| **置信度标注** | LLM prompt 约束 | high/medium/low + EXTRACTED/INFERRED |
| **操作日志增强** | `src/db/repository.py` | log.md + operation_log 表双写 |

### 面试可讲

- "我用了 SHA256 哈希做增量缓存，避免重复处理相同内容"
- "我参考了 nashsu/llm_wiki 的两步 CoT 设计，先分析再生成"
- "每次摄入后 LLM 会自动更新全局综述，让 wiki 保持全局视角"

---

## Phase 3：Query 查询 + API 完善

> **状态**：⬜ 未开始
> **对标**：nashsu v0.2-v0.3

### 目标

wiki 写进去了，要能查出来——实现基于 index.md 的导航式查询。

### 功能清单

| 功能 | 文件 | 说明 |
|------|------|------|
| **Query 查询** | `src/core/wiki_compiler.py` | 读 index.md → 定位相关页 → 遍历 wikilinks → 综合回答 |
| **GET /v1/query** | `src/main.py` | API 端点，返回带引用的答案 |
| **答案归档** | `src/tools/write_tool.py` | 有价值的查询结果存回 wiki/queries/ |
| **GET /v1/pages** | `src/main.py` | 列出所有 wiki 页面 |
| **GET /v1/pages/{path}** | `src/main.py` | 读取单个 wiki 页面 |
| **搜索（基础）** | `src/tools/search_tool.py` | 文件名+标题关键词搜索 |

### 面试可讲

- "查询不是 RAG 式的 chunk 检索，而是基于 wiki 页面级别的导航查询"
- "LLM 先读 index.md 定位候选页面，再遍历 wikilinks 深入，最后综合回答"
- "好的答案可以归档回 wiki，不沉没在聊天记录中"

---

## Phase 4：知识图谱 + Lint 检查

> **状态**：⬜ 未开始
> **对标**：nashsu v0.3-v0.4

### 目标

让 wiki 的连接关系可视化，并具备自我诊断能力。

### 功能清单

| 功能 | 文件 | 说明 |
|------|------|------|
| **Wikilinks 解析器** | `src/core/graph.py` | 正则解析所有 wiki 页面的 `[[links]]` |
| **知识图谱 JSON** | `src/core/graph.py` | 节点+边数据，输出为 JSON |
| **图谱可视化 HTML** | `static/graph.html` | 自包含 HTML（vis.js/D3.js），双击打开 |
| **Lint 检查** | `src/core/linter.py` | 断链检测、孤页检测、矛盾检测 |
| **GET /v1/lint** | `src/main.py` | API 端点，返回检查报告 |
| **GET /v1/graph** | `src/main.py` | API 端点，返回图谱数据 |
| **矛盾标记系统** | LLM prompt + frontmatter | 摄入时标记 ⚠️ 矛盾 |
| **密码保护** | `src/core/auth.py`（新） | 私人数据密码验证解锁，API 中间件 |

### 知识图谱两遍构建

```
第一遍（确定性）: 正则解析 [[wikilinks]] → 显式边
第二遍（语义性）: LLM 推断隐式关系 → 隐式边（带置信度）
```

### 面试可讲

- "知识图谱采用两遍构建法——确定性解析 + 语义推断"
- "Lint 不是简单的断链检查，还包括矛盾检测和知识缺口识别"
- "图谱可视化是自包含 HTML 文件，无需服务器，双击即可浏览"

---

## Phase 5：搜索增强 + MCP Server + 面试打磨

> **状态**：⬜ 未开始
> **对标**：nashsu v0.5 / cobusgreyling v0.2 MCP

### 目标

达到面试竞争力——搜索、Agent 集成、完整的文档和测试。

### 功能清单

| 功能 | 说明 |
|------|------|
| **BM25 搜索** | 关键词全文搜索，tantivy 或 whoosh |
| **向量搜索（可选）** | embedding + LanceDB/ChromaDB |
| **混合搜索** | BM25 + 向量 RRF 融合 |
| **MCP Server** | 让 Claude Code/Cursor 等 Agent 可以查询 wiki |
| **Deep Research（可选）** | LLM 自动搜索网络补充知识缺口 |
| **Web Clipper（可选）** | 浏览器剪藏插件 |
| **完整测试覆盖** | 单元测试 + 集成测试 + 边界情况 |
| **API 文档** | OpenAPI/Swagger 完善 |
| **演示数据** | 准备 10-20 个源文件 + 生成的 wiki 展示 |

### 面试可讲

- "我实现了混合搜索——BM25 关键词 + 向量语义，RRF 融合排序"
- "通过 MCP Server，外部 AI Agent 可以直接查询我的 wiki"
- "完整的测试覆盖和 API 文档"

---

## 面试就绪标准

### 最低面试标准（Phase 4 完成时）

✅ 能演示的功能：
1. 上传一篇技术文章 → LLM 自动生成带 `[[wikilinks]]` 的 wiki 页面
2. 上传第二篇相关文章 → LLM 更新已有页面并标记矛盾
3. 通过 API 查询 → LLM 遍历 wiki 页面综合回答
4. 打开 graph.html → 看到知识图谱可视化
5. 调用 /v1/lint → 看到 wiki 健康检查报告

✅ 能讲清楚的设计决策：
1. 为什么是三层架构而不是 RAG？（编译器 vs 解释器）
2. 为什么 LLM 只写 wiki/ 不写 raw/？（不可变事实基准）
3. 两步 CoT 为什么比单步好？（理解与写作分离）
4. 知识图谱两遍构建的原理？
5. 安全模型如何防止路径穿越？

✅ 代码质量：
- pytest 测试覆盖率 > 80%
- 所有函数有 type hints + docstring
- 错误处理覆盖 4 种 HTTP 状态码
- README 有清晰的架构图和快速开始指南

### 加分项（面试中脱颖而出的点）

| 加分项 | 难度 | 说明 |
|--------|------|------|
| MCP Server 集成 | 中 | 演示 "Claude Code 查询我的 wiki" |
| 两步 CoT 摄入 | 中 | 原创性设计，不是简单的 prompt engineering |
| 知识图谱两遍构建 | 中 | 确定性+语义性双通道 |
| 矛盾标记系统 | 低 | 简单的 prompt 约束 + frontmatter 字段 |
| SHA256 增量缓存 | 低 | 工程实用性 |
| 向量混合搜索 | 高 | LanceDB/ChromaDB 集成 |

---

## 预估时间线

| 阶段 | 预估时间 | 里程碑 |
|------|---------|--------|
| Phase 1 | 1-2 周（剩余） | `POST /v1/ingest` 端到端跑通 |
| Phase 2 | 2-3 周 | 增强摄入 + 完整元数据 |
| Phase 3 | 2-3 周 | Query + API 完善 |
| Phase 4 | 3-4 周 | 知识图谱 + Lint |
| Phase 5 | 3-5 周 | 搜索 + MCP + 面试打磨 |
| **合计** | **约 11-17 周** | 达到面试就绪 |

> ⚠️ 这是保守估计。nashsu 从 0 到 v0.5（我们的 Phase 4 水平）用了约 3 个月高频迭代。

---

## 开发流程约定

**核心理念**：

> 面试不是 Phase 5 才准备的事情。每个 Phase 的实现过程中，你已经在积累面试素材了。Phase 结束时做复盘，是把"我都做完了"变成"我都能讲清楚"。**Claude 用引导式提问（苏格拉底式），你先自己思考口述，我再帮你核对。这样你面试时讲的是你自己的话，不是背我的稿子。**

---

### 约定一：中期对标参考项目

**触发时机**：Phase 3 完成时（或 Phase 3 中期）。

**方法论**：

```
第一轮：AI 先做架构梳理
  1. Claude 分析参考项目的目录结构、模块划分、数据流
  2. 输出参考项目的"模块清单 + 功能点清单"

第二轮：逐模块比对
  对每个模块分类：
    ├── ❌ 我没有 → 列为 Phase 4-5 开发候选
    └── ✅ 我也有 → 比对实现方式差异，记录谁的设计更好、为什么

第三轮：差距总结
  输出对比报告，调整 Phase 4-5 优先级
```

**具体执行**：

1. 下载并本地运行 **nashsu/llm_wiki**（桌面应用）或 **cobusgreyling/llm-wiki**（Python CLI）
2. Claude 先抓取参考项目的源码结构，梳理出完整的模块清单
3. 用相同的测试数据（10-20 篇源文件），分别在两个系统上执行 Ingest
4. 逐模块对比：

| 对比维度 | 我的项目 | 参考项目 | 分类 | 行动 |
|----------|---------|---------|------|------|
| Ingest 质量 | ? | ? | ✅/❌ | 参考 / 开发 |
| 页面结构 | ? | ? | ✅/❌ | 参考 / 开发 |
| Wikilinks 密度 | ? | ? | ✅/❌ | ... |
| 元数据完整度 | ? | ? | ✅/❌ | ... |
| 查询体验 | ? | ? | ✅/❌ | ... |
| 知识图谱 | ? | ? | ✅/❌ | ... |
| Lint 能力 | ? | ? | ✅/❌ | ... |

5. 输出对比报告 → 调整 Phase 4-5 的优先级

**为什么是 Phase 3 结束后**：

- Phase 1-3 完成后你有了完整的 "Ingest → Query" 闭环，才能和参考项目做有效对比
- Phase 4-5 开始前发现差距，还来得及调整方向
- 太早对比（Phase 1-2）你的功能太少，对比没有意义
- 太晚对比（Phase 5）没时间改了

**参考项目选择建议**：

- 首选 **cobusgreyling/llm-wiki**：Python 实现，技术栈一致，代码可以直接对比
- 其次 **nashsu/llm_wiki**：功能最全（12,500+ stars），但它是 React+Rust 桌面应用，代码层面差异大，重点比功能和设计

---

### 约定二：Phase 结束时，引导式面试复盘

**触发时机**：每个 Phase 的最后一个 task 完成时。

**流程**：

```
1. Claude 主动提醒："Phase X 已完成，现在进行面试复盘。"
2. Claude 提出 3-5 个引导式问题（只问不答），例如：
   - "这个阶段你做了什么？用一句话概括。"
   - "你做的 X 功能，和传统 RAG 的做法有什么不同？"
   - "如果面试官问你'为什么选择 Y 方案而不是 Z'，你怎么回答？"
   - "这个阶段的哪个设计决策你觉得最有面试价值？"
3. 用户口述回答（Claude 不打断、不提示）
4. 用户说"我讲完了"后，Claude 逐条核对：
   - ✅ 正确的部分 — 确认并可能补充亮点
   - ⚠️ 需要修正的部分 — 给出修正建议和更好的表述
   - ❌ 遗漏的部分 — 补充用户没提到的关键点
5. 核对结果写入 `.specify/interview-notes/phase-X-review.md`

---

## 当前优先事项

**本周目标（Phase 1 收尾）**：

1. 完成 `WikiCompiler.ingest()` 核心逻辑
2. 通过 `POST /v1/ingest` 调通端到端流程
3. 写一个简单的集成测试验证
4. 所有现有测试通过 `pytest`

**下周目标（Phase 2 启动）**：

1. 实现 SHA256 增量缓存
2. LLM prompt 中要求输出 wikilinks 和 frontmatter
3. 实现 index.md 自动更新
