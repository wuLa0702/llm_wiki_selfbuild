# Phase 3 方案设计自检报告

> 触发：约定三 — 方案设计完成后、编码开始前，对照参考项目逐项检查
> 日期：2026-07-07

---

## 参考项目版本

| 项目 | 版本 | Stars | 技术栈 |
|------|------|-------|--------|
| nashsu/llm_wiki | v0.3.13 | ~13,000 | Tauri v2 + Rust/React |
| cobusgreyling/llm-wiki | v0.2.1 | ~200 | Python CLI (npm) |

---

## 功能对照表

| 功能 | nashsu v0.3 | cobusgreyling v0.2 | 我 Phase 3（初版） | 我 Phase 3（修正） | 判定 |
|------|:--:|:--:|:--:|:--:|---|
| Ingest 摄入 | ✅ 两步 CoT | ✅ | ✅ Phase 1-2 完成 | 不变 | ✅ |
| SHA256 缓存 | ✅ | ✅ | ✅ Phase 2 完成 | 不变 | ✅ |
| **Query 查询** | ✅ 4-phase pipeline | ✅ ReAct agent | ✅ 3-step | ✅ 3-step + 图扩展 | ✅ 修正后覆盖 |
| **答案归档** | ✅ --save | ✅ auto-save | ✅ archive=True | 不变 | ✅ |
| **页面列表/详情 API** | ✅ HTTP API | ✅ wiki list/expand | ✅ /v1/pages | 不变 | ✅ |
| **Token 追踪** | ❌ | ❌ | ✅ TokenTracker | 不变 | ➕ 我独有 |
| **Wikilinks 图解析** | ✅ 4-signal 模型 | ✅ 确定性解析 | ❌ Phase 4 | ✅ WikiGraph | 🔴→✅ 修正 |
| **静态 Lint** | ✅ 含在 lint | ✅ lint --skip-llm | ❌ Phase 4 | ✅ LintTool | 🔴→✅ 修正 |
| **关键词搜索** | ✅ CJK bigram | ✅ BM25 | 🟡 SQLite LIKE | 不变 | 🟡 降级版 |
| **LLM 语义 Lint** | ✅ 矛盾检测 | ✅ | ❌ Phase 4 | 不变 | 🟡 可接受 |
| **MCP Server** | ✅ 6+ tools | ✅ 6 tools | ❌ Phase 5 | 不变 | 🟡 可接受 |
| **图谱可视化** | ✅ sigma.js | ❌ | ❌ Phase 4 | 不变 | 🟡 可接受 |
| **向量搜索** | ✅ LanceDB | ❌ | ❌ Phase 5 | 不变 | 🟡 可接受 |

---

## 发现的两个关键缺失与修正

### 🔴 缺失 1：Wikilinks 图解析器

**参考项目**：
- nashsu v0.3: 4-signal 相关性模型（直接链接 ×3.0、来源重叠 ×4.0、Adamic-Adar ×1.5、类型亲和 ×1.0）
- cobusgreyling v0.2: Query 时遍历 wikilinks 发现相关页面

**我的初版设计**：Query 只靠 index.md 标题匹配 + 关键词搜索定位候选页面。

**问题**：只能找到"包含关键词"的页面，找不到"不包含关键词但被 wikilinks 关联指向"的页面。这是 LLM Wiki 比 RAG 的核心优势之一——知识连接已编译在 wikilinks 中，Query 不用是浪费。

**修正**：Phase 3 新增 **第三步（Wikilinks 图解析器）**——`WikiGraph` 确定性正则解析 + 邻接表构建，Query 用 `neighbors(candidates, depth=1)` 扩展候选页。

**成本**：零 LLM 调用，1000 页内 < 100ms。

**学习价值**：面试可以讲 "我做了图解析器来做 Query 的候选页面扩展——不靠向量相似度，靠已经编译好的 wikilinks 连接关系。这是 LLM Wiki 和 RAG 的区分点。"

---

### 🔴 缺失 2：静态 Lint 检查

**参考项目**：
- cobusgreyling v0.2: `lint --skip-llm` 做断链、孤页、索引缺失检测

**我的初版设计**：Lint 全部放在 Phase 4。

**问题**：断链和孤页检测是**纯确定性算法**（正则 + 集合运算），零 LLM 成本。Phase 3 已经有 `WikiGraph` 数据了，不做 Lint 是浪费已有的图结构。

**修正**：Phase 3 新增 **第五步（静态 Lint 检查）**——断链检测、孤页检测、索引缺失检测、健康评分。

**成本**：零 LLM 调用，完全基于 `WikiGraph` 和文件系统数据。

**学习价值**：面试可以讲 "我在 Phase 3 就加入了静态 Lint——断链检测和孤页检测不需要 LLM，纯确定性算法。LLM 语义 Lint（矛盾检测）放在 Phase 4。"

---

## 未修正的差距（有意识的降级）

### 🟡 关键词搜索：SQLite LIKE vs BM25

- nashsu: CJK bigram 分词 + stop word 去除
- cobusgreyling: BM25 with title/header boosting
- 我：SQLite `LIKE` + 文件名匹配

**不修正理由**：BM25 需要额外依赖（`rank_bm25` 或 `whoosh`），且 SQLite LIKE 对 100-200 页的 wiki 足够用。BM25 升级延后到 Phase 5。

### 🟡 LLM 语义 Lint：延后到 Phase 4

- 两个参考项目都有 LLM 矛盾检测
- 我延后到 Phase 4

**不修正理由**：语义 Lint 需要 LLM 调用（有成本），且需要先有静态 Lint 的基础。Phase 3 做完静态 Lint 后，Phase 4 加语义 Lint 是自然的扩展。

### 🟡 MCP Server：延后到 Phase 5

**不修正理由**：MCP 需要项目功能基本稳定后才能做。Phase 3 还在加 Query/Lint 核心功能，MCP 过早。

---

## 修正总结

| 修正项 | 初版 | 修正后 | 新增文件 | 估时增加 |
|--------|------|--------|---------|---------|
| Wikilinks 图解析器 | ❌ 无 | ✅ WikiGraph | `src/core/graph.py` | +1-2 天 |
| 静态 Lint 检查 | ❌ Phase 4 | ✅ Phase 3 | `src/core/linter.py` | +1 天 |
| Query 定位策略 | 关键词 + index | 关键词 + index + **图扩展** | 修改 `wiki_compiler.py` | +0.5 天 |

**总估时**：7-10 天 → 9-14 天。增加 2-4 天，但核心能力大幅提升。

---

## 自检经验教训

### 教训 1：确定性算法不应无理由延后

wikilinks 解析和静态 lint 都是零 LLM 成本的确定性算法。把它们放在 Phase 4 的唯一理由是"Phase 4 叫知识图谱 + Lint"，但这个名字是人为划分的——实际上，基础版本完全可以在 Phase 3 做。

**规则**：如果某功能（1）确定性实现（2）零 LLM 成本（3）对当前阶段有直接帮助 → 不应该延后。

### 教训 2：对照参考项目不是为了抄，是为了发现设计盲区

nashsu 和 cobusgreyling 已经把 LLM Wiki 从概念做到产品了。他们为什么在 v0.2-v0.3 就做了图解析？因为图结构是 Query 的基础设施——没有图，Query 只是"关键词搜索 + LLM 总结"，和有图的"导航式查询"是两种完全不同的体验。

### 教训 3：Phase 边界应该是功能边界，不是文件名边界

我最初的想法是"graph.py 属于 Phase 4，所以 Phase 3 不碰"。但正确的思考方式是：**graph.py 的确定性部分（正则解析）属于 Phase 3，语义部分（LLM 推断隐式边）属于 Phase 4。** 一个文件可以跨 Phase 演进。
