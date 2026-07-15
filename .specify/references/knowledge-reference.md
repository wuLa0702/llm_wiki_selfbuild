# LLM Wiki 知识点与面试参考手册

> **目的**：系统性地整理 LLM Wiki 项目中涉及的核心概念、技术知识点和理念，为面试准备提供知识储备和参考来源。
>
> **用法**：
> - 面试前通读一遍，确保能讲清楚每个概念
> - 每个概念都有"面试怎么讲"——用简洁的中文讲给面试官
> - 每个知识点都有参考链接，想深入时点进去看

---

## 第一部分：核心操作概念

### 1. Ingest（摄入）

**定义**：将原始素材（raw/）"编译"为结构化 Wiki 页面（wiki/）的过程。

**详细流程**：
1. 读取 raw/ 下的源文件
2. LLM 分析：提取实体（人/组织/工具）、概念（方法/理论）、核心观点
3. LLM 检测与现有 wiki 内容的矛盾
4. LLM 生成 wiki 页面：来源摘要 + 实体页 + 概念页
5. 更新 index.md（目录）、log.md（日志）、overview.md（综述）
6. 一个源文件可能触及 10-15 个 wiki 页面

**关键洞察**（区别于 RAG）：
- RAG 是"解释器模式"：每次查询重新发现知识，无积累
- LLM Wiki 是"编译器模式"：摄入时一次性编译，知识复利增长

**面试怎么讲**：
> "Ingest 是 LLM Wiki 的核心操作。当用户把一篇文章放进 raw/ 目录后，LLM 会完整阅读它，提取实体、概念和关键观点，然后生成或更新多个 wiki 页面。这与传统 RAG 的根本区别在于——RAG 是每次查询时从原始文档中临时检索片段，而 LLM Wiki 是一次性编译为结构化知识，后续查询直接基于已编译的 wiki 页面。知识会复利增长。"

**参考链接**：
- [Karpathy 原始 Gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [nashsu 的两步 CoT 实现](https://github.com/nashsu/llm_wiki#3-two-step-chain-of-thought-ingest)

---

### 2. Query（查询）

**定义**：基于已编译的 wiki 页面进行知识检索和综合回答。

**详细流程**：
1. LLM 先读 index.md 定位候选页面
2. 读候选页面，通过 `[[wikilinks]]` 遍历关联页面
3. 综合多页面信息，生成带引用的答案
4. 有价值的答案可归档回 wiki/queries/

**与 RAG Query 的区别**：

| 维度 | RAG Query | LLM Wiki Query |
|------|-----------|----------------|
| 检索单元 | 向量分块（chunks） | 结构化 wiki 页面 |
| 知识积累 | 无，每次从零开始 | 有，基于已有编译结果 |
| 交叉引用 | 每次查询时重新发现 | 摄入时预构建 |
| 引用来源 | chunk 片段 | 完整 wiki 页面 |

**面试怎么讲**：
> "查询不是直接去 raw/ 里搜原始文档，而是基于已编译的 wiki 页面。LLM 先读 index.md 了解有哪些相关页面，然后逐个阅读，通过 wikilinks 深入关联页面，最后综合所有信息给出答案。这比 RAG 的优势在于——wiki 页面已经是经过 LLM 提炼的结构化知识，而不是原始文本片段。"

**参考链接**：
- [nashsu 的查询检索管道](https://github.com/nashsu/llm_wiki#7-optimized-query-retrieval-pipeline)

---

### 3. Lint（检查）

**定义**：对 Wiki 进行健康检查，发现断链、孤页、矛盾、知识缺口等问题。

**检查项**：

| 检查类型 | 说明 |
|----------|------|
| **断链检测** | `[[wikilinks]]` 指向不存在的页面 |
| **孤页检测** | 没有任何入站链接的页面 |
| **矛盾检测** | 两个页面对同一事实的说法不一致 |
| **缺失实体** | 被多次提及但没有独立页面的重要概念 |
| **知识缺口** | 大量引用但缺乏深入讨论的话题 |
| **过时内容** | 被新来源推翻但未更新的声明 |

**面试怎么讲**：
> "Lint 是 LLM Wiki 的自我诊断机制。与传统 wiki 不同，LLM Wiki 的 Lint 不是简单的断链检查——它还包括语义层面的分析，比如检测两个页面的矛盾声明、发现被反复提及但缺少独立页面的重要概念。这就像代码的 lint 工具，但针对的是知识质量。"

**参考链接**：
- [Karpathy 的 Lint 流程描述](https://github.com/NousResearch/hermes-agent/blob/main/skills/research/llm-wiki/SKILL.md)

---

### 4. Compile（编译）

**定义**：Ingest 的批量形式——一次性读取所有 raw/ 源文件，做跨文件综合和全局重组。

**与 Ingest 的区别**：
- Ingest：增量处理单个新源文件
- Compile：批量重新处理所有源文件，发现跨文件的综合主题

**面试怎么讲**：
> "Compile 是 Ingest 的批量模式。当用户积累了足够多的源文件后，可以触发一次全局编译——LLM 会重新阅读所有源文件，发现跨文件的主题和模式，创建综合页面。这体现了'编译器'的核心比喻。"

**参考链接**：
- [pith 项目的 compile pass 设计](https://github.com/abhisekjha/pith)

---

## 第二部分：架构设计理念

### 5. RAG vs LLM Wiki（编译器 vs 解释器）

这是面试中**最重要**的对比，必须讲清楚。

| 维度 | RAG（解释器模式） | LLM Wiki（编译器模式） |
|------|------------------|----------------------|
| 知识处理时机 | 查询时实时重新发现 | 摄入时一次性编译 |
| 是否积累 | 无，每次从零开始 | 有复利效应，越用越丰富 |
| 存储单元 | 向量分块（chunks） | 结构化 Markdown wiki 页面 |
| 交叉引用 | 每次查询重新发现 | 摄入时预构建 `[[wikilinks]]` |
| 人类角色 | 上传 + 提问 | 策展 + 探索 |
| LLM 角色 | 检索 + 总结 | 撰写 + 交叉引用 + 维护 |
| 矛盾发现 | 查询时偶然发现 | 摄入时主动标记 |
| 规模化 | 线性增长 | 复利增长 |

**面试怎么讲**：
> "我用一个计算机科学的类比来解释——RAG 是解释器模式：每次查询都是一次全新的'解释执行'，从原始文档中临时检索、临时推理、临时组织答案。而 LLM Wiki 是编译器模式：在摄入源文件时，LLM 像编译器一样把它'编译'为结构化的 wiki 页面，生成实体页、概念页、交叉引用。之后的每次查询都运行在已编译的知识上，不需要重新推导。这就是为什么 LLM Wiki 有复利效应——第 100 篇文章的摄入受益于前 99 篇已编译的知识。"

**参考链接**：
- [GreenNode: Distill, Don't Chunk and Vector](https://greennode.ai/tutorial/building-a-personal-llm-wiki-part-1-distill-dont-chunk-and-vector)
- [知乎: Karpathy LLM Wiki 编译器模式](https://zhuanlan.zhihu.com/p/2026769881924675536)

---

### 6. 三层架构

```
raw/   ← 不可变事实基准（人类策展）
wiki/  ← LLM 编译的知识产物（LLM 维护）
schema ← 行为约束规则（人类+LLM 共演进）
```

**为什么三层分离重要**：
- raw/ 不可变 → wiki 出错可以从 raw/ 重建
- wiki/ LLM 专属 → 人类不需要写 wiki，只需要策展和提问
- schema 可演进 → 你和 LLM 一起发现什么规则有效，逐步优化

**面试怎么讲**：
> "三层架构是 LLM Wiki 最核心的设计决策。第一层 raw/ 是不可变的原始素材——这是事实基准，wiki 出任何问题都可以从这里重建。第二层 wiki/ 完全由 LLM 维护——人类只读不写。第三层 schema 是约束规则——它告诉 LLM 怎么组织知识、用什么格式、遵循什么命名规范。这三层各自独立、可以分别替换。"

**参考链接**：
- [Karpathy 原始架构描述](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [nashsu 的实现](https://github.com/nashsu/llm_wiki#what-we-kept-from-the-original)

---

### 7. Wikilinks 与双向链接

**定义**：使用 `[[page-name]]` 语法在 wiki 页面间建立显式交叉引用。

**双向链接的价值**：
- 人类浏览：点击跳转，类似维基百科
- 机器解析：正则即可提取所有链接关系，构建知识图谱
- 知识发现：反向链接（哪些页面链接到了我）揭示隐式关联

**面试怎么讲**：
> "Wikilinks 是 LLM Wiki 的毛细血管系统。我要求 LLM 在生成每个页面时都使用 `[[双向链接]]` 引用相关页面。这有两个好处——一是人类浏览时可以像维基百科一样跳转，二是机器可以通过正则解析所有链接关系来构建知识图谱。不需要额外的 NLP 分析，确定性解析就能拿到页面关系。"

**参考链接**：
- [Obsidian 内部链接语法](https://help.obsidian.md/Linking+notes+and+files/Internal+links)

---

### 8. 矛盾标记

**定义**：在摄入阶段，当新来源与已有 wiki 内容冲突时，主动标记矛盾。

**为什么在摄入时而非查询时**：
- RAG 的矛盾发现是被动的、偶然的
- LLM Wiki 的矛盾标记是主动的、系统性的
- 矛盾不会在多次查询后被遗忘

**面试怎么讲**：
> "传统 RAG 中矛盾是被动发现的——只有当你恰好问到矛盾涉及的问题时，才可能发现两个来源说法不一。而 LLM Wiki 在摄入时就主动对比新来源与已有知识，如果发现矛盾立即标记。这不只是一个功能，而是知识质量保证的系统性方法。"

**参考链接**：
- [SamurAIGPT 的矛盾标记设计](https://github.com/SamurAIGPT/llm-wiki-agent)

---

## 第三部分：技术知识点

### 9. 两步 Chain-of-Thought（CoT）摄入

**原理**：将 LLM 的摄入任务拆分为两个独立调用，各司其职。

```
Step 1（分析）: 专注理解
  - 输入：源文件内容 + wiki 现有状态
  - 输出：结构化分析（实体列表、概念列表、与现有知识的关联和矛盾）

Step 2（生成）: 专注写作
  - 输入：Step 1 的分析结果
  - 输出：实际写入的 wiki 页面
```

**为什么比单步好**：
- 单步 prompt 中 LLM 同时做"理解"和"写作"，容易混淆
- 两步分离后，每步的 prompt 更聚焦，输出质量更高
- Step 1 的分析结果可以用于人类的 intermediate review

**面试怎么讲**：
> "普通做法是把源文件扔给 LLM，让它直接生成 wiki 页面。我参考了 nashsu/llm_wiki 的做法，拆成两步——第一步 LLM 只做分析，输出结构化的分析结果；第二步 LLM 基于分析结果做生成。这就像写文章前先列大纲——分析和写作分离后，每一步的 prompt 更聚焦，生成质量明显提升。"

**参考链接**：
- [nashsu 的两步 CoT 设计文档](https://github.com/nashsu/llm_wiki#3-two-step-chain-of-thought-ingest)
- [Chain-of-Thought 论文](https://arxiv.org/abs/2201.11903)

---

### 10. SHA256 增量缓存

**原理**：对源文件内容计算 SHA256 哈希，只处理内容发生变化的文件。

```
source_file → SHA256(content) → 对比上次记录的哈希
  ├── 相同 → 跳过（节省 LLM tokens）
  └── 不同 → 重新摄入 + 更新哈希记录
```

**面试怎么讲**：
> "这是一个工程优化——每次摄入前对源文件做 SHA256 哈希，如果文件没变就跳过。这在批量处理时特别有用，避免了重复调用 LLM 产生的费用和延迟。是生产级系统的必要设计。"

**参考链接**：
- [nashsu 的 SHA256 增量缓存实现](https://github.com/nashsu/llm_wiki#3-two-step-chain-of-thought-ingest)

---

### 11. 知识图谱构建

**两遍构建法**：

| 遍次 | 方法 | 输入 | 输出 |
|------|------|------|------|
| **第一遍**（确定性） | 正则匹配 `[[wikilinks]]` | 所有 wiki 页面 | 节点 + 显式边 |
| **第二遍**（语义性） | LLM 分析页面内容 | 页面文本对 | 隐式关系边 |

**相关性信号（nashsu 的 4 信号模型）**：
- **直接链接** (×3.0)：`[[wikilinks]]` 显式引用
- **来源重叠** (×4.0)：两个页面来自同一原始来源
- **Adamic-Adar** (×1.5)：共享共同邻居（按邻居度加权）
- **类型亲和** (×1.0)：同类型页面间的自然亲和

**社区发现**：
- Louvain 算法 → 自动发现知识聚类
- 凝聚力评分 → 评估社区紧凑程度
- 交叉社区边 → 发现意外关联

**面试怎么讲**：
> "知识图谱不是简单地把 wikilinks 画成图——我用两遍构建法。第一遍是确定性的，正则解析所有页面的 wikilinks，得到显式的引用关系。第二遍是语义性的，让 LLM 分析没有直接链接但内容相关的页面，发现隐式关系。这样既保证了确定性引用关系的准确性，又能发现人类可能忽略的隐性关联。"

**参考链接**：
- [nashsu 的 4 信号相关性模型](https://github.com/nashsu/llm_wiki#4-knowledge-graph-with-relevance-model)
- [Louvain 算法论文](https://arxiv.org/abs/0803.0476)
- [sigma.js 图可视化库](https://www.sigmajs.org/)

---

### 12. 混合搜索（Hybrid Search）

**原理**：结合关键词搜索（BM25）和语义搜索（向量 embedding），取长补短。

**BM25（关键词搜索）**：
- 优点：精确匹配、速度快、对专有名词好
- 缺点：不理解语义，同义词失效

**向量搜索（语义搜索）**：
- 优点：理解语义相似性，同义词可匹配
- 缺点：对精确术语匹配不如 BM25

**RRF（Reciprocal Rank Fusion）融合**：
```
score = 1/(k + BM25_rank) + 1/(k + Vector_rank)
```

**面试怎么讲**：
> "纯关键词搜索找不到语义相关但用词不同的内容，纯向量搜索可能漏掉精确术语匹配。我用 RRF 把两者融合——BM25 保证精确匹配，向量搜索补充语义相似性，取长补短。"

**参考链接**：
- [BM25 算法说明](https://en.wikipedia.org/wiki/Okapi_BM25)
- [RRF 融合算法](https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf)

---

### 13. MCP Server（Model Context Protocol）

**定义**：一个标准化协议，让外部 AI Agent（Claude Code、Cursor、Codex 等）可以通过统一的工具接口访问你的 wiki。

**典型的 MCP 工具**：

| 工具名 | 功能 |
|--------|------|
| `wiki_search` | 搜索 wiki 内容 |
| `wiki_expand` | 读取指定页面（含目录） |
| `wiki_list` | 按类型列出页面 |
| `wiki_lint` | 运行健康检查 |
| `wiki_stats` | 统计信息 |
| `wiki_graph` | 查询图谱关系 |

**面试怎么讲**：
> "我实现了 MCP Server，让 Claude Code 等外部 AI Agent 可以通过标准协议查询我的 wiki。这意味着用户不需要打开我的应用——他们可以在自己的 AI 编程助手里直接问'我的 wiki 里关于 Transformer 有哪些内容'，Agent 会自动调用我的 MCP 工具来获取答案。这是 LLM Wiki 作为基础设施层的设计理念。"

**参考链接**：
- [MCP 官方文档](https://modelcontextprotocol.io/)
- [cobusgreyling 的 MCP 实现](https://github.com/cobusgreyling/llm-wiki)

---

### 14. 安全模型：路径校验

**核心原则**：基于目录的权限隔离。

**防御手段**：
1. **路径前缀校验**：检查最终路径是否在允许的目录前缀内
2. **路径穿越防御**：`os.path.normpath()` 规范化 + 拒绝 `../`
3. **白名单模式**：只允许访问明确声明的目录

**面试怎么讲**：
> "LLM 本质上是不可控的——它可能尝试写入任意路径。我的安全模型基于白名单——raw/ 只读、wiki/ 可写、其他目录不可访问。每次工具调用都做路径前缀校验和穿越防御。这不是过度设计，而是 LLM 应用的基本安全需求。"

**参考链接**：
- 本项目 `.claude/rules/00-security.md`

---

### 15. YAML Frontmatter 元数据

**每个 wiki 页面的结构**：

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
# 页面正文开始...
```

**元数据的作用**：
- `type`：页面类型分类（entity/concept/source/synthesis）
- `tags`：标签分类，支持 Dataview 等 Obsidian 插件查询
- `sources`：反向追溯到原始素材
- `confidence`：LLM 对内容的可信度自我评估

**面试怎么讲**：
> "每个 wiki 页面都有结构化的 YAML frontmatter。我特别设计了 sources 字段——每个页面都反向追溯到它来自哪些原始素材。这样当原始素材更新或删除时，我可以精确定位需要更新的 wiki 页面。"

**参考链接**：
- [Obsidian YAML frontmatter 文档](https://help.obsidian.md/Editing+and+formatting/Properties)

---

### 16. LangChain 在本项目中的角色

**项目定位**：本项目使用 LangChain 作为 LLM 调用的**标准封装层**，而非全套框架。

**核心理念**：用 LangChain 的"乐高积木"，但不被 LangChain 的"整套玩法"绑架。

**为什么选 LangChain 而不是直接调 HTTP API**：

| 对比 | 直接调 HTTP API | 用 LangChain |
|------|----------------|-------------|
| Provider 切换 | 每个 Provider 写一套代码 | 统一接口，改个参数即可 |
| Prompt 管理 | 字符串拼接，难以维护 | `ChatPromptTemplate` 模板化管理 |
| 结构化输出 | 手动解析 JSON | `StructuredOutputParser` + Pydantic |
| 可观测性 | 自己写日志 | LangSmith / Callbacks 自动追踪 |
| 学习成本 | 低 | 中（但本项目只用子集） |

**本项目的 LangChain 使用策略**：

```
只用这些 ────────────────────── 不用这些
✅ ChatOpenAI / ChatDeepSeek    ❌ LangChain Agents
✅ ChatPromptTemplate           ❌ LangGraph
✅ SystemMessage/HumanMessage   ❌ LCEL 复杂链
✅ StrOutputParser              ❌ VectorStore (本项目不用)
✅ StructuredOutputParser       ❌ LangChain Hub
✅ Callbacks (Phase 4+)         ❌ Memory (本项目自己管理)
```

**面试怎么讲**：
> "项目中我用 LangChain 做了一个薄封装层，主要目的是 Provider 抽象和 Prompt 模板化管理。很多人用 LangChain 会把整套 Agents、Chains、Memory 全引进来，但我有意保持克制——只用了模型调用、Prompt 管理、输出解析这三个核心能力。这样既享受了 LangChain 的标准化优势，又不会因为框架太厚重导致调试困难。"

**每阶段 LangChain 学习重点**：

| 阶段 | 需要学的 LangChain 概念 | 用在哪里 |
|------|------------------------|---------|
| **Phase 1** | `ChatOpenAI`、`ChatDeepSeek`、`.invoke()` | 基础 LLM 调用（已实现） |
| **Phase 2** | `ChatPromptTemplate`、`SystemMessage`、`HumanMessage`、`StrOutputParser` | 管理 ingest prompt 模板 |
| **Phase 3** | `StructuredOutputParser`、`PydanticOutputParser` | 让 LLM 输出结构化 JSON（实体列表、分析结果） |
| **Phase 4** | `RunnableSequence`（简单链式调用） | 两步 CoT 的串联 |
| **Phase 5** | `BaseCallbackHandler` | 日志追踪、token 统计、LLM 调用耗时监控 |

**学习路线建议**：

```
Phase 1-2：先看 LangChain 官方 Quickstart
  └── https://python.langchain.com/docs/get_started/quickstart

Phase 2-3：重点学 PromptTemplate + OutputParser
  └── https://python.langchain.com/docs/modules/model_io/prompts/
  └── https://python.langchain.com/docs/modules/model_io/output_parsers/

Phase 4-5：学 Callbacks 做可观测性
  └── https://python.langchain.com/docs/modules/callbacks/
```

**⚠️ LangChain 学习中的坑（避免浪费时间）**：

1. **不要学 LangChain Expression Language (LCEL) 的复杂用法** — 你的链最多 2-3 步，不需要 `|` 管道嵌套
2. **不要学 LangChain Agents / Tools 体系** — 你已经有自己的 Tool 层（ReadTool/WriteTool），不需要 LangChain 的 Agent 框架
3. **不要学 LangGraph** — 那是给复杂多 Agent 工作流用的，本项目不需要
4. **不要追 LangChain 版本更新** — 锁定一个稳定版本（如 0.3.x），专注于你需要的功能

**参考链接**：
- [LangChain 官方 Quickstart](https://python.langchain.com/docs/get_started/quickstart)
- [LangChain Prompt Templates](https://python.langchain.com/docs/modules/model_io/prompts/)
- [LangChain Output Parsers](https://python.langchain.com/docs/modules/model_io/output_parsers/)
- [LangChain Callbacks](https://python.langchain.com/docs/modules/callbacks/)

---

## 第四部分：面试高频问题准备

### Q1："你的项目和 LangChain 的 RAG 有什么不同？"

**回答框架**：
1. **根本哲学不同**：RAG 是"检索-回答"模式（解释器），LLM Wiki 是"编译-查询"模式（编译器）
2. **知识是否积累**：RAG 每次查询从零开始推导，LLM Wiki 知识逐次复利增长
3. **人类角色不同**：RAG 中人类被动提问，LLM Wiki 中人类主动策展和探索
4. **适用场景不同**：RAG 适合一次性文档问答，LLM Wiki 适合长期知识积累

### Q2："LLM 生成的内容不可靠，你怎么保证 wiki 质量？"

**回答框架**：
1. **置信度标注**：LLM 对每条声明标注 high/medium/low
2. **来源追溯**：每个 wiki 页面通过 sources 字段追溯到原始素材
3. **矛盾标记**：摄入时主动检测冲突，标注 ⚠️ 矛盾
4. **Lint 检查**：定期健康检查，发现断链、孤页、过时声明
5. **人类在回路**：人类策展 raw/ 目录（选择可信来源），schema 定义质量标准

### Q3："如果 wiki 出错了，怎么修复？"

**回答框架**：
1. **重建能力**：raw/ 不可变，wiki 出问题可以从 raw/ 重新编译
2. **Git 版本控制**：wiki 是纯 Markdown 文件，git 管理所有变更历史
3. **增量更新**：SHA256 哈希确保只重新处理变化的源文件
4. **人类干预**：可以手动编辑 wiki 页面，也可以调整 schema 让 LLM 重新生成

### Q4："你的技术选型为什么是 Python + FastAPI？"

**回答框架**：
1. **FastAPI**：自动生成 OpenAPI 文档、Pydantic 校验、异步支持
2. **SQLite**：零配置、嵌入式、适合个人知识库的规模
3. **Markdown**：纯文本格式，Git 友好、Obsidian 兼容、无供应商锁定
4. **差异化**：大多数 LLM Wiki 框架是 Agent Skill 或桌面应用，我的 API 服务形态更灵活

### Q5："你怎么处理 LLM 的输出不稳定问题？"

**回答框架**：
1. **结构化 prompt**：明确的 system prompt + schema 约束
2. **结构化输出**：要求 LLM 按 YAML frontmatter + Markdown 格式输出
3. **验证层**：写入前校验页面类型、文件名、禁止内容
4. **重试机制**：LLM 调用有 timeout 和 max_retries
5. **两步 CoT**：分离分析和生成，每步更聚焦

### Q6："你为什么用 LangChain？直接用 OpenAI/DeepSeek 的 HTTP API 不行吗？"

**回答框架**：
1. **Provider 抽象**：LangChain 统一了 OpenAI、DeepSeek、豆包等多家的调用接口。换模型只改变量，不改代码
2. **Prompt 管理**：`ChatPromptTemplate` 让 system prompt 和 user prompt 分离管理，比字符串拼接更专业
3. **但保持克制**：我只用了 LangChain 的模型调用、Prompt 管理、输出解析三个核心模块。故意没有用 Agents、Chains、Memory——那些会让项目过度依赖框架
4. **面试官追问"为什么不直接用 HTTP API"**：可以说 "LangChain 的 PromptTemplate 和 OutputParser 帮我省了大量字符串解析和格式化代码。而且结构化输出（配合 Pydantic）让 LLM 返回的不再是自由文本，而是可以程序化处理的 JSON——这对两步 CoT 摄入至关重要"

---

## 第五部分：推荐学习资源

### 必读

| 资源 | 链接 | 为什么重要 |
|------|------|-----------|
| Karpathy LLM Wiki Gist | https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f | 原始设计文档，理念源头 |
| nashsu/llm_wiki README | https://github.com/nashsu/llm_wiki | 最完整实现的设计文档 |
| GreenNode: Distill, Don't Chunk | https://greennode.ai/tutorial/building-a-personal-llm-wiki-part-1-distill-dont-chunk-and-vector | 深入对比 RAG vs LLM Wiki |

### 深入阅读

| 资源 | 链接 | 主题 |
|------|------|------|
| SamurAIGPT llm-wiki-agent | https://github.com/SamurAIGPT/llm-wiki-agent | 知识图谱两遍构建 |
| cobusgreyling/llm-wiki | https://github.com/cobusgreyling/llm-wiki | Python 实现 + MCP |
| NousResearch Hermes LLM Wiki Skill | https://github.com/NousResearch/hermes-agent/blob/main/skills/research/llm-wiki/SKILL.md | Ingest/Query/Lint 流程 |
| Joi 的 LLM Wiki 分析 | https://gist.github.com/Joi/120f86eb39758ef75deb5e6145e5a717 | 批判性视角 |
| 知乎: LLM Wiki 编译器模式 | https://zhuanlan.zhihu.com/p/2026769881924675536 | 中文深度解读 |

### 技术参考

| 资源 | 链接 | 主题 |
|------|------|------|
| MCP 官方文档 | https://modelcontextprotocol.io/ | Agent 集成协议 |
| Obsidian 内部链接语法 | https://help.obsidian.md/Linking+notes+and+files/Internal+links | Wikilinks 标准 |
| sigma.js 图可视化 | https://www.sigmajs.org/ | 知识图谱前端 |
| BM25 算法 | https://en.wikipedia.org/wiki/Okapi_BM25 | 关键词搜索 |
| Chain-of-Thought 论文 | https://arxiv.org/abs/2201.11903 | CoT 理论基础 |
| Louvain 社区发现 | https://arxiv.org/abs/0803.0476 | 图谱聚类算法 |
| RRF 融合 | https://plg.uwaterloo.ca/~gvcormac/cormacksig09-rrf.pdf | 混合搜索融合 |
| LangChain Quickstart | https://python.langchain.com/docs/get_started/quickstart | LangChain 快速入门 |
| LangChain Prompt Templates | https://python.langchain.com/docs/modules/model_io/prompts/ | Prompt 模板化管理 |
| LangChain Output Parsers | https://python.langchain.com/docs/modules/model_io/output_parsers/ | 结构化输出解析 |
| LangChain Callbacks | https://python.langchain.com/docs/modules/callbacks/ | LLM 调用追踪与监控 |

---

## 为什么这份文档放在 `.specify/` 下

1. `.specify/` 是本项目的设计规格目录，已有 `001-整体架构设计.md` 和 `roadmap-phase1.md`
2. 这份文档本质上是"面试知识规格"——定义了项目涉及的核心概念和设计决策
3. 开发时参考它来确保每个功能都被正确理解和实现
4. 面试前重温它来确保能讲清楚每个设计决策的 why
