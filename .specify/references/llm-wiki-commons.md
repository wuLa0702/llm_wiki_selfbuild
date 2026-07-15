# LLM Wiki 框架共性提取

> 来源：分析 7+ 个 LLM Wiki 开源框架（nashsu/llm_wiki、SamurAIGPT/llm-wiki-agent、sdyckjq-lab/llm-wiki-skill、cobusgreyling/llm-wiki、pi-llm-wiki、sage-wiki、llm-wiki-compiler）后提取的最大公约数。

---

## 一、架构共性：三层模型

**所有框架无一例外采用三层分离：**

```
知识库根目录/
├── raw/          # 第1层：不可变原始素材（LLM 只读，人类策展）
├── wiki/         # 第2层：LLM 生成和维护的结构化知识
└── schema/       # 第3层：约束 LLM 行为的规则/配置
```

### 各层职责

| 层 | 谁写 | 职责 |
|----|------|------|
| `raw/` | 人类 | 策展原始素材（文章、论文、PDF、笔记），不可变 |
| `wiki/` | LLM | 创建/更新/交叉引用所有知识页面，人类只读 |
| `schema/` | 人类+LLM | 定义页面结构、命名规范、标签体系、页面类型约束 |

### 为什么分层重要（面试可讲）

- **第1层是事实基准**：如果 wiki 出问题，可以从 raw/ 重建
- **第2层是编译产物**：LLM 拥有完全所有权，人类不需要写 wiki
- **第3层是纪律约束**：把 LLM 从通用聊天机器人转变为有纪律的 wiki 维护者
- **每层可独立替换**：任何 Markdown 阅读器都能替代 Obsidian，Claude Code 可换成 OpenAI Codex

> **我们的项目已天然支持前两层。第三层用 `CLAUDE.md` + `.claude/rules/` 承载。**

---

## 二、页面分类体系

所有框架都使用相似的类型划分：

| 类型 | 目录 | 含义 | 本项目的状态 |
|------|------|------|-------------|
| **实体页** | `entities/` | 人、组织、工具、产品、模型 | ✅ 已有 |
| **概念页** | `concepts/` | 思想、方法、框架、理论 | ✅ 已有 |
| **来源摘要** | `sources/` | 每个原始来源的结构化摘要 | ❌ 待添加 |
| **综合/对比** | `synthesis/` 或 `comparisons/` | 跨来源综合分析 | ❌ 待添加 |
| **索引** | `index.md` | 全局目录，每次摄入更新 | ❌ 待添加 |
| **日志** | `log.md` | 追加式操作记录 | ✅ 已有（wiki/log.md） |
| **全局综述** | `overview.md` | 跨所有来源的综合论述 | ❌ 待添加 |

---

## 三、核心操作三元组：Ingest → Query → Lint

这是所有框架共享的核心操作模型：

```
Ingest（摄入）  →  读 raw/ → LLM 分析提取 → 写 wiki/ → 更新元数据
Query（查询）   →  读 index.md → 遍历 [[wikilinks]] → 综合多页面 → 生成答案
Lint（检查）   →  遍历 wiki/ → 检测矛盾/断链/孤页/缺失 → 生成报告
```

### Ingest 的详细流程（共性）

1. 读取 raw/ 下的源文件
2. LLM 分析提取：实体、概念、核心观点、与其他源的矛盾
3. LLM 生成 wiki 页面：来源摘要 + 实体页 + 概念页（一次摄入可能触及 10-15 个页面）
4. 更新 index.md（目录）和 log.md（操作记录）
5. 更新 overview.md（全局综述）
6. 标记矛盾（如有）

### 两步 CoT（Chain-of-Thought）摄入 — nashsu 的关键创新

```
Step 1（分析）: LLM 读取源文件 → 结构化分析
  - 关键实体、概念、论点
  - 与现有 wiki 内容的关联
  - 与现有知识矛盾/张力
  - wiki 结构建议

Step 2（生成）: LLM 基于分析结果 → 生成 wiki 文件
  - 来源摘要页
  - 实体/概念页及交叉引用
  - 更新 index.md / log.md / overview.md
```

> **面试亮点**：分两步比单步 prompt 质量高很多——第一步聚焦"理解"，第二步聚焦"写作"，各司其职。

---

## 四、双向链接（Wikilinks）

**所有框架都使用 `[[page-name]]` 语法**，这是 Obsidian 生态的事实标准：

```markdown
# 示例：Transformer 页面
Transformer 由 [[entities/Vaswani.md|Vaswani]] 在 2017 年提出，
核心机制是 [[concepts/self_attention.md|Self-Attention]]。
```

### Wikilinks 的双重价值

| 价值 | 说明 |
|------|------|
| **导航** | 人类浏览时一键跳转 |
| **图谱** | 解析 wikilinks 即可构建知识图谱，无需 LLM |

> **我们的项目应在 LLM 的 system prompt 中要求它输出 `[[链接]]` 格式。**

---

## 五、元数据层（YAML Frontmatter）

每个 wiki 页面都包含 frontmatter 元数据：

```yaml
---
title: "Transformer 架构"
type: concept
created: 2026-07-06
updated: 2026-07-06
tags: [deep-learning, attention, nlp]
sources:
  - raw/sources/attention-is-all-you-need.md
confidence: high
---
```

**共性字段**：`title`、`type`、`created`、`updated`、`tags`、`sources`

---

## 六、增量缓存（SHA256）

几乎所有完整实现都使用 **SHA256 哈希** 做增量缓存：

```
源文件 → SHA256(content) → 对比上次哈希
  ├── 相同 → 跳过，不浪费 LLM tokens
  └── 不同 → 重新摄入
```

> **面试亮点**：这是生产级特性，避免重复处理相同内容和浪费 API 费用。

---

## 七、知识图谱

所有框架都提供知识图谱可视化。两遍构建法是共性设计：

### 两遍构建

| 遍次 | 方法 | 产出 |
|------|------|------|
| **确定性解析** | 正则匹配 `[[wikilinks]]` | 显式边，tag=EXTRACTED |
| **语义推断** | LLM 分析页面内容 | 隐式关系边，tag=INFERRED/AMBIGUOUS |

### 相关性信号（nashsu 的 4 信号模型）

| 信号 | 权重 | 含义 |
|------|------|------|
| 直接链接 | ×3.0 | 通过 `[[wikilinks]]` 相连 |
| 来源重叠 | ×4.0 | 共享同一原始来源 |
| Adamic-Adar | ×1.5 | 共享共同邻居（按邻居度加权） |
| 类型亲和 | ×1.0 | 同类型页面加分 |

### 社区发现

使用 **Louvain 算法** 自动发现知识聚类，揭示隐式主题分组。

> **面试亮点**：两遍构建 = 确定性 + 语义性，展示你对 pipeline 设计的理解。

---

## 八、矛盾标记机制

**多个框架在摄入时标记矛盾，而非查询时才发现：**

```markdown
⚠️ 矛盾：来源 A 声称 X，但来源 B 声称 Y。
需要进一步验证。
```

这比传统 RAG 的"查询时偶然发现矛盾"强很多。

---

## 九、Obsidian 兼容性

所有框架都兼容 Obsidian：
- Markdown + `[[wikilinks]]` 是 Obsidian 原生格式
- YAML frontmatter 被 Obsidian 原生支持
- 自动生成 `.obsidian/` 配置目录
- 知识图谱与 Obsidian Graph View 互补

---

## 十、MCP Server / Agent 集成

成熟的框架都提供 MCP Server，让外部 AI Agent（Claude Code、Codex 等）可以查询 wiki：

| 框架 | MCP 工具数量 | 关键工具 |
|------|-------------|---------|
| cobusgreyling/llm-wiki | 6 | search, expand, list, lint, stats, recent_log |
| nashsu/llm_wiki | 多个 | search, files, graph, reviews, sources/rescan |

---

## 十一、安全模型（我们已具备）

| 目录 | 权限 | 说明 |
|------|------|------|
| `raw/` | **只读** | LLM 绝不修改原始素材 |
| `wiki/` | **读写** | LLM 自由创建/更新知识页 |
| `src/` | **只读** | 代码由人类维护 |
| `.claude/` | **只读** | 规则配置由人类维护 |

路径前缀校验、路径穿越防御——我们的 `.claude/rules/00-security.md` 已完美覆盖。

---

## 十二、共性总结：最小可行产品（MVP）必须具备的能力

| 优先级 | 能力 | 说明 |
|--------|------|------|
| **P0** | 三层架构 | raw/ 只读 + wiki/ 读写 + schema 约束 |
| **P0** | Ingest 摄入 | LLM 读源文件 → 生成 wiki 页面 |
| **P0** | 页面分类 | entities / concepts / sources 三类 |
| **P0** | Wikilinks | `[[双向链接]]` 交叉引用 |
| **P0** | 安全模型 | 路径校验 + 权限隔离 |
| **P1** | 两步 CoT 摄入 | 分析 → 生成两阶段 |
| **P1** | SHA256 缓存 | 增量摄入，避免重复 |
| **P1** | 元数据层 | SQLite 记录页面和链接关系 |
| **P1** | 矛盾标记 | 摄入时标记冲突 |
| **P2** | 知识图谱 | wikilinks 解析 + 可视化 |
| **P2** | Lint 检查 | 断链/孤页/矛盾检测 |
| **P2** | MCP Server | Agent 集成 |
| **P3** | 向量搜索 | 混合检索（BM25 + embedding） |
| **P3** | Web Clipper | 浏览器剪藏 |
| **P3** | Deep Research | 自动搜索补充知识 |

---

## 参考来源

- [Karpathy 原始 LLM Wiki Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [nashsu/llm_wiki](https://github.com/nashsu/llm_wiki) — 最完整实现，12,500+ stars
- [SamurAIGPT/llm-wiki-agent](https://github.com/SamurAIGPT/llm-wiki-agent) — 设计文档最佳
- [sdyckjq-lab/llm-wiki-skill](https://github.com/sdyckjq-lab/llm-wiki-skill) — 中文场景优化
- [cobusgreyling/llm-wiki](https://github.com/cobusgreyling/llm-wiki) — Python 技术栈参考
