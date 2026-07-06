# Phase 2 — 增强摄入 + 元数据完善

> **状态**：🟡 进行中
> **对标**：nashsu v0.2 / cobusgreyling v0.2
> **前置**：Phase 1 完成（POST /v1/ingest 端到端跑通）
>
> 完整路线图：[roadmap.md](roadmap.md)

---

## 目标

把 Phase 1 的"能跑通"升级为"能生产用"：

- LLM 摄入质量大幅提升（两步 CoT：先分析再生成）
- 重复文件不浪费 tokens（SHA256 增量缓存）
- wiki 导航体系自动维护（index.md / overview.md / log.md）
- 每篇 wiki 页面的内容可校验、可追溯
- Prompt 工程模板化（不再硬编码字符串拼接）

---

## 依赖链

```
Phase 1 产物（WikiCompiler.ingest + API + SQLite）
        │
        ▼
第一步：Prompt 模板化           ← src/llm/prompts.py（重构）
        │
        ▼
第二步：两步 CoT 摄入           ← src/core/wiki_compiler.py（核心重构）
        │
        ▼
第三步：导航文件自动维护          ← src/core/wiki_compiler.py
        │
        ▼
第四步：SHA256 增量缓存          ← src/core/cache.py（新文件）
        │
        ▼
第五步：内容质量校验             ← src/core/validator.py（新文件）
        │
        ▼
第六步：配置与质量信号           ← purpose.md（新文件）+ prompts 增强
```

**从下往上，逐层验证。**

---

## 第一步：Prompt 模板化

> Phase 1 的 System Prompt 是字符串常量，Phase 2 需要支持模板变量（如动态注入现有 wiki 页面列表）。

**文件：** `src/llm/prompts.py`

### 1.1 拆分 Ingest Prompt 为两步

- [ ] 定义 `SYSTEM_PROMPT_INGEST_ANALYZE`
  - 角色：知识分析器
  - 输入：源文件内容 + 现有 wiki index.md（上下文）
  - 输出要求：**严格的 JSON 结构**
    ```json
    {
      "entities": [{"name": "", "type": "", "importance": "high/medium/low"}],
      "concepts": [{"name": "", "description": "", "related_to": []}],
      "contradictions": [{"claim": "", "existing_page": "", "description": ""}],
      "connections_to_existing": [{"topic": "", "wiki_page": "", "relation": ""}],
      "recommendations": ["建议1", "建议2"]
    }
    ```
  - 强调"只分析不写作"——禁止生成 Markdown 页面内容

- [ ] 定义 `SYSTEM_PROMPT_INGEST_GENERATE`
  - 角色：Wiki 页面生成器
  - 输入：Step 1 的分析结果（JSON）+ 源文件内容
  - 输出格式：---PAGE:...---（保持 Phase 1 的 PAGE/END 格式）
  - 新增要求：
    - 每个页面必须包含 **YAML frontmatter**（title, type, tags, sources, confidence）
    - 每个页面至少 2 个 `[[wikilinks]]` 出站链接
    - 置信度标注：`high`（原文明确陈述） / `medium`（合理推断） / `low`（推测）

### 1.2 使用 LangChain ChatPromptTemplate（可选优化）

- [ ] 将 System Prompt 和 User Prompt 分离
  ```python
  from langchain.prompts import ChatPromptTemplate
  from langchain.schema import SystemMessage, HumanMessage

  # 不再用字符串拼接，改为模板
  analyze_template = ChatPromptTemplate.from_messages([
      ("system", SYSTEM_PROMPT_INGEST_ANALYZE),
      ("human", "源文件内容：\n\n{source_content}"),
  ])
  ```

> ⚠️ 此优化可延后到 Phase 3（当需要 `StructuredOutputParser` 时一起做）。本阶段重点是把 Prompt 内容写好。

### 验证

- [ ] 单独测试 Step 1 Prompt：给定源文件 → LLM 返回合法 JSON
- [ ] 单独测试 Step 2 Prompt：给定分析 JSON → LLM 返回带 frontmatter 的页面

---

## 第二步：两步 CoT 摄入

**文件：** `src/core/wiki_compiler.py`

### 2.1 重构 `ingest()` 流程

- [ ] 原有单步 ingest 改名为 `ingest_simple()`（保留兼容）
- [ ] 新增 `ingest()` 使用两步 CoT 流程：
  1. 读取 `wiki/index.md` 获取现有 wiki 上下文
  2. **Step 1 — 分析**：`LLMAdapter.chat(source_content, SYSTEM_PROMPT_INGEST_ANALYZE)`
     - prompt 中包含现有 index.md（让 LLM 知道 wiki 里已经有什么）
  3. 解析 Step 1 输出为 JSON（`json.loads()`，带异常处理）
  4. **Step 2 — 生成**：`LLMAdapter.chat(json.dumps(analysis), SYSTEM_PROMPT_INGEST_GENERATE)`
     - 同时传入原始源文件内容作为参考
  5. 解析 Step 2 输出（`_parse_response()`），写文件 + 记录元数据

- [ ] Step 1 JSON 解析失败时的降级策略：
  ```python
  try:
      analysis = json.loads(response)
  except json.JSONDecodeError:
      # 降级为单步模式
      logger.warning("Step 1 输出非 JSON，降级为单步 ingest")
      return self.ingest_simple(source_path)
  ```

### 2.2 增强 LLMAdapter

**文件：** `src/llm/adapter.py`

- [ ] 实现 `chat_structured(prompt, system_prompt, output_schema) → dict`
  - 通过 LangChain `PydanticOutputParser` 或 `JsonOutputParser`
  - 用于 Step 1 的 JSON 输出（保证格式正确）
  - 如果 LangChain 版本不支持，则用 `chat()` + `json.loads()` 兜底

### 验证

- [ ] Step 1 输出是合法 JSON，包含 entities/concepts/contradictions 字段
- [ ] Step 2 生成的页面包含 YAML frontmatter
- [ ] 降级策略生效：JSON 失败时自动切换单步模式

---

## 第三步：Wiki 导航文件自动维护

**文件：** `src/core/wiki_compiler.py`

### 3.1 index.md 自动更新

**当前问题**：`wiki/index.md` 是手动创建的，统计数字是 0。

- [ ] 实现 `_update_index()` 方法：
  1. 查询 `WikiRepository` 统计各类型页面数量
  2. 列出最近更新的 20 个页面（title + path + date）
  3. 按 entity / concept / source 分组输出目录
  4. 写入 `wiki/index.md`

  输出格式：
  ```markdown
  # Wiki 全局索引

  > 自动维护 — 每次 Ingest 后更新

  ## 统计
  - 实体数：12
  - 概念数：18
  - 源文档数：3
  - 最后更新：2026-07-06 15:30

  ## 实体目录
  - [[entities/xxx.md|XXX]] — 一句话简介

  ## 概念目录
  - [[concepts/yyy.md|YYY]] — 一句话简介

  ## 源文档摘要
  - [[sources/zzz.md|ZZZ]] — 一句话简介
  ```

### 3.2 overview.md 自动生成

- [ ] 实现 `_update_overview()` 方法：
  - 调用 LLM 读取 index.md → 生成全局综述
  - Prompt 要求 LLM 综合所有来源，总结主题分布、核心发现、知识缺口
  - 写入 `wiki/overview.md`

### 3.3 log.md 格式修正

**当前问题**：log 条目附加在旧内容前面，导致 "Wiki 操作日志" 标题出现在文件末尾。

- [ ] 修正 `_update_log()`：
  - 首次写入：创建 `# Wiki 操作日志\n\n` 标题
  - 后续写入：新条目插入到标题之后、旧内容之前
  - 统一格式：
    ```markdown
    ## [2026-07-06] ingest | 源文件名

    **Source:** `raw/sources/xxx.md`
    **Pages created:** entities/aaa.md, concepts/bbb.md
    **Pages updated:** concepts/ccc.md
    **Conflicts:** 无
    ```

### 验证

- [ ] 执行一次 ingest → `wiki/index.md` 统计数字正确
- [ ] `wiki/overview.md` 生成非空内容
- [ ] `wiki/log.md` 格式正确，标题在顶部

---

## 第四步：SHA256 增量缓存

**新文件：** `src/core/cache.py`

### 4.1 缓存管理器

- [ ] 实现 `class IngestCache`：
  ```python
  class IngestCache:
      """基于 SHA256 的源文件增量缓存"""

      def __init__(self, db_path: str = "wiki.db"):
          ...

      def hash_file(self, file_path: str) -> str:
          """计算文件的 SHA256 哈希"""
          ...

      def has_changed(self, source_path: str) -> bool:
          """检测源文件内容是否变化。未变 → False，已变/新文件 → True"""
          ...

      def mark_ingested(self, source_path: str) -> None:
          """记录摄入后的哈希值"""
          ...
  ```

- [ ] 缓存数据存储在 SQLite `ingest_cache` 表中（`src/db/schema.py` 新增表）：
  ```sql
  CREATE TABLE IF NOT EXISTS ingest_cache (
      source_path TEXT PRIMARY KEY,
      sha256_hash TEXT NOT NULL,
      ingested_at TEXT NOT NULL DEFAULT (datetime('now'))
  );
  ```

### 4.2 集成到 WikiCompiler.ingest()

- [ ] 在 `ingest()` 开头调用 `cache.has_changed(source_path)`：
  - `False` → 跳过，返回 `{"status": "skipped", "message": "Source unchanged"}`
  - `True` → 继续执行 ingest，完成后 `cache.mark_ingested()`

### 验证

- [ ] 同一源文件连续 ingest 两次 → 第二次返回 "skipped"
- [ ] 修改源文件内容 → 再次 ingest → 正常处理
- [ ] 新增源文件 → 正常处理并记录哈希

---

## 第五步：内容质量校验

**新文件：** `src/core/validator.py`

### 5.1 WikiValidator 校验器

- [ ] 实现 `class WikiValidator`：
  ```python
  class WikiValidator:
      """Wiki 页面内容校验器"""

      VALID_TYPES = ["entity", "concept", "source", "query", "synthesis"]

      @staticmethod
      def validate_path(path: str) -> None:
          """校验页面路径：不能空、不能 ../、必须在允许的目录下"""

      @staticmethod
      def validate_frontmatter(content: str) -> dict:
          """校验 YAML frontmatter：必须有 title, type；type 在合法范围内"""

      @staticmethod
      def validate_no_executable(content: str) -> None:
          """禁止内容：<script>、<iframe>、javascript: 链接"""

      @staticmethod
      def validate_wikilinks(content: str) -> list[str]:
          """检查至少有 1 个 wikilink（Phase 2 放宽为至少 1 个）"""
  ```

### 5.2 集成到 WriteTool

**文件：** `src/tools/write_tool.py`

- [ ] 在 `write_page()` 中增加可选校验参数：
  ```python
  def write_page(self, relative_path: str, content: str, validate: bool = True) -> str:
      if validate:
          WikiValidator.validate_path(relative_path)
          WikiValidator.validate_frontmatter(content)
          WikiValidator.validate_no_executable(content)
      # ... 原有写入逻辑
  ```

### 验证

- [ ] 写入带 `<script>` 的内容 → 抛出异常
- [ ] 写入不带 frontmatter 的内容 → 抛出异常（或警告日志）
- [ ] 正常内容 → 写入成功

### 5.3 隐私标记与访问控制

> 核心原则：**不拦截，全量生成，按标记限制访问。**

**设计理念**：内容不管公开还是隐私，知识价值是一样的——区别只在于"谁能看"。

**与之前方案的关键差异**：

| | 旧方案（5.3+5.4） | 新方案 |
|---|---|---|
| Ingest 行为 | 隐私内容拦截，不生成 wiki | ✅ 全量生成，不拦截 |
| 谁能决定隐私 | LLM 判断 | ✅ **用户定义规则**（API 录入） |
| 关联行为 | — | 常规页面可 `[[wikilink]]` 关联，但点击跳转需密码 |
| 密码 | Phase 4 一起做 | Phase 2 **不实现**密码验证 |

#### 5.3.1 用户定义隐私规则

**当前版本（Phase 2）**：使用默认关键词库，初始化项目时自动写入数据库。

**默认隐私关键词**：

```yaml
# 情感与关系
emotion:
  - 情感    - 恋爱    - 失恋    - 暗恋    - 分手
  - 情侣    - 配偶    - 前任    - 相亲    - 表白
  - 心碎    - 孤独感  - 抑郁    - 焦虑症  - 心理诊断

# 财务
financial:
  - 银行卡   - 账户金额 - 存款    - 工资    - 理财
  - 信用卡   - 贷款    - 负债    - 投资    - 密码
  - 支付宝   - 微信支付

# 个人身份
identity:
  - 身份证   - 手机号   - 住址    - 户籍
  - 护照     - 车牌号   - 社保号  - 学号

# 健康
health:
  - 病历     - 体检    - 手术    - 诊断书
  - 药物     - 过敏史  - 家族病史
```

**未来版本（Phase 4+）**：支持用户手动确认和编辑规则。

- [ ] `GET /v1/privacy/rules` — 查看当前规则（含默认 + 用户自定义）
- [ ] `POST /v1/privacy/rules/confirm` — 用户确认/修改默认规则
  ```json
  {
    "keyword": "情感",
    "action": "keep"   // keep | remove | recategorize
  }
  ```
- [ ] 默认关键词初始化逻辑与用户修改记录分离（`is_default` 字段标记）

- [ ] 隐私规则存储到 SQLite（`src/db/schema.py` 新增表）：

  ```sql
  CREATE TABLE IF NOT EXISTS privacy_rules (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      keyword TEXT NOT NULL UNIQUE,
      category TEXT DEFAULT 'general',
      is_default INTEGER DEFAULT 1,   -- 1=默认规则，0=用户自定义
      created_at TEXT NOT NULL DEFAULT (datetime('now'))
  );

  CREATE TABLE IF NOT EXISTS privacy_categories (
      name TEXT PRIMARY KEY,
      label TEXT NOT NULL
  );
  ```

- [ ] 实现 `PrivacyManager`（`src/core/privacy.py`）：

  ```python
  class PrivacyManager:
      """隐私规则管理器"""

      def add_rule(self, keyword: str, category: str = "general") -> None: ...
      def remove_rule(self, keyword: str) -> None: ...
      def list_rules(self) -> list[dict]: ...
      def match(self, content: str) -> list[dict]:
          """
          检测内容命中的隐私规则

          Returns:
              [{"keyword": "恋爱", "category": "relationship"}, ...]
              空列表表示未命中任何隐私规则
          """
  ```

#### 5.3.2 Ingest 流程整合

**全部识别，全部生成，按标记区分：**

```
源文件
  → Step 1 分析
  → PrivacyManager.match()  ← 用户定义的规则
      ├── 命中 → 标记为 restricted
      └── 未命中 → 正常 ingest
  → Step 2 生成 wiki 页面
      ├── 普通页面：frontmatter visibility: public
      └── 隐私页面：frontmatter visibility: restricted + privacy_categories: ["emotion"]
```

- [ ] 隐私页面的 frontmatter 标记：

  ```yaml
  ---
  title: "情感管理笔记"
  type: concept
  visibility: restricted              # 关键字段
  privacy_categories: [emotion]        # 命中的隐私类别
  sources:
    - raw/sources/personal-journal.md
  confidence: medium
  ---
  ```

#### 5.3.3 页面关联规则

**常规页面可以 `[[wikilink]]` 关联隐私页面，链接存在但不跳转：**

```markdown
# 常规页面：时间管理

时间管理和 [[concepts/情绪管理.md|情绪]] 密切相关。
  ↑
  这个 wikilink 被正常渲染为链接
  但点击后 → 密码验证 → 通过才可查看
```

- [ ] API 读取 `visibility: restricted` 的页面时：
  - `GET /v1/pages/{path}` → 返回 `{"status": "locked", "message": "此页面为个人隐私存储，需要密码验证"}`
  - 验证密码后返回正文内容

- [ ] `_extract_links()` 正常提取 wikilinks（不论目标页面是什么 visibility）
  - 链接关系照常存入 `page_links` 表
  - 知识图谱中显示为"受限关联"（虚线边）

#### 5.3.4 本阶段交付 vs 延后

| 功能 | Phase 2 | 说明 |
|------|---------|------|
| ✅ 隐私规则 API（CRUD） | 实现 | `POST/GET/DELETE /v1/privacy/rules` |
| ✅ 规则存储 | 实现 | SQLite `privacy_rules` + `privacy_categories` |
| ✅ PrivacyManager | 实现 | 关键词匹配 + 语义分类 |
| ✅ Ingest 标记 | 实现 | frontmatter `visibility: restricted` |
| ✅ wikilink 关联 | 实现 | 正常关联，不阻断 |
| ❌ 密码验证 | **延时** | Phase 4 的 `auth.py`，含 API 中间件 |
| ❌ 页面加密存储 | **延时** | Phase 5+，当前明文 |
| ❌ 密码管理 UI | **延时** | 本阶段仅 API |

> 密码功能的具体实现放在 Phase 4，参见 [roadmap.md Phase 4 密码保护条目](roadmap.md)。

---

## 第六步：配置与质量信号

### 6.1 Purpose.md

**新文件：** 项目根目录 `purpose.md`

- [ ] 创建 `purpose.md`，定义知识库的目标和范围：
  ```markdown
  # LLM Wiki — 知识库目标

  ## 研究方向
  - 个人成长与自我管理
  - 认知科学与学习方法
  - AI/LLM 技术与应用

  ## 核心问题
  - 如何建立有效的个人知识管理体系？
  - LLM 如何辅助知识的内化和应用？
  - ...

  ## 收录标准
  - 与研究方向直接相关的优质内容
  - 有明确观点或方法论的内容
  - 避免纯新闻/资讯类内容
  ```

- [ ] 在 `ingest()` 中，Step 1 的 prompt 包含 `purpose.md` 内容（让 LLM 知道知识库的方向）

### 6.2 Prompt 中强制 YAML Frontmatter

**文件：** `src/llm/prompts.py`

- [ ] 在 `SYSTEM_PROMPT_INGEST_GENERATE` 中明确要求：
  ```markdown
  ## YAML Frontmatter 要求（必须）

  每个页面必须包含：
  ```yaml
  ---
  title: "页面标题"
  type: concept  # entity / concept / source / query
  created: 2026-07-06
  tags: [tag1, tag2]
  sources:
    - raw/sources/源文件名.md
  confidence: high  # high / medium / low
  ---
  ```
  ```

### 6.3 置信度标注体系

- [ ] 在 Prompt 中定义置信度使用规则：
  - `high` — 原文明确陈述的事实
  - `medium` — 基于原文的合理推断
  - `low` — LLM 的背景知识补充

- [ ] 在 `IngestResponse` 中新增 `confidence_summary` 字段（可选）：
  ```python
  class IngestResponse(BaseModel):
      ...
      confidence_summary: dict[str, int] = {}  # {"high": 5, "medium": 3, "low": 1}
  ```

### 验证

- [ ] purpose.md 存在且非空
- [ ] 新生成的页面包含 frontmatter（title, type, tags, sources, confidence）
- [ ] 不同页面出现不同的 confidence 值

---

## 验证标准（端到端）

```bash
# 1. 第一次 Ingest（无缓存）
curl -X POST http://localhost:8000/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"source_path": "sources/atomic-habits.md"}'
# → 执行两步 CoT，返回 pages_created + confidence_summary

# 2. 第二次 Ingest（缓存命中）
curl -X POST http://localhost:8000/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"source_path": "sources/atomic-habits.md"}'
# → 返回 status: "skipped"

# 3. 检查导航文件
cat wiki/index.md       # 统计数字正确，页面列表完整
cat wiki/overview.md    # 有全局综述内容
head -30 wiki/log.md    # 格式正确，标题在顶部

# 4. 检查生成页面质量
head -10 wiki/concepts/xxx.md  # 有 YAML frontmatter
grep "\[\[" wiki/concepts/xxx.md  # 有 wikilinks

# 5. 安全校验
# 尝试写入含 <script> 的页面 → 被拒

# 6. API 文档
curl http://localhost:8000/docs  # Swagger 可查看所有端点
```

---

## 本阶段 LangChain 学习重点

| 概念 | 用于什么 | 优先级 |
|------|---------|--------|
| `ChatPromptTemplate` | Prompt 模板管理 | 🔴 必学 |
| `SystemMessage` / `HumanMessage` | 分离系统指令和用户输入 | 🔴 必学 |
| `StrOutputParser` | 获取 LLM 的纯文本输出 | 🟡 推荐 |
| `JsonOutputParser` / `PydanticOutputParser` | Step 1 的结构化 JSON 输出 | 🟡 推荐 |
| `RunnableSequence` | 简单链式串联（后面阶段用） | 🟢 可选 |

> 详见 [knowledge-reference.md](knowledge-reference.md) 第 16 节。

---

## 交付物

Phase 2 完成时：

- [ ] `POST /v1/ingest` 使用两步 CoT 摄入（分析 → 生成）
- [ ] 每个 wiki 页面包含 YAML frontmatter（title, type, tags, sources, confidence）
- [ ] SHA256 增量缓存生效：相同文件不重复处理
- [ ] `wiki/index.md` 每次摄入后自动更新（带实时统计）
- [ ] `wiki/overview.md` 自动生成全局综述
- [ ] `wiki/log.md` 格式正确（标题在顶部，条目可 grep 解析）
- [ ] `purpose.md` 存在，LLM 每次摄入时读取
- [ ] 内容校验器拦截不合规页面（禁止脚本、强制 frontmatter）
- [ ] `pytest` 新测试覆盖两步 CoT、缓存、校验
- [ ] 已有 wiki 页面的 index.md 统计为正确数字（不为 0）
