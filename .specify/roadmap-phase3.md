# Phase 3 — Query 查询 + Token 治理 + API 完善

> **状态**：⬜ 未开始
> **对标**：nashsu v0.3 / cobusgreyling v0.2
> **前置**：Phase 2 完成（两步 CoT + 缓存 + 导航文件 + 隐私标记）
>
> 完整路线图：[roadmap.md](roadmap.md)

---

## 目标

Phase 1-2 完成了"写"的能力，Phase 3 聚焦"读"：

- wiki 写进去了，要能**查出来**——实现基于页面导航的 Query（非 RAG）
- 知道每次操作**花了多少 tokens**——Token 治理透明化
- API 体系补全——JSON 格式的页面列表/详情/搜索 API

---

## 依赖链

```
Phase 2 产物（CoT ingest + 缓存 + 导航文件 + index.md）
        │
        ▼
第一步：Token 使用量追踪          ← src/llm/adapter.py（基础设施）
        │
        ▼
第二步：搜索能力补齐              ← src/tools/search_tool.py + src/db/repository.py
        │
        ▼
第三步：Query 查询引擎            ← src/core/wiki_compiler.py（核心功能）
        │
        ▼
第四步：API 端点完善              ← src/main.py（对外接口）
        │
        ▼
第五步：答案归档                  ← src/core/wiki_compiler.py（知识沉淀）
```

**Token 追踪必须先做**——后续所有 LLM 调用都能自动记录消耗，开发调试时就能看到成本。

---

## 第一步：Token 使用量追踪

> **背景**：当前 LLMAdapter 调用后不记录 token 消耗，导致 ¥25/天的消耗无法定位来源。
> **目标**：每次 LLM 调用自动记录 input/output tokens，汇聚到 API 可查询。

**文件：** `src/llm/adapter.py` + 新文件 `src/core/token_tracker.py`

### 1.1 从 LangChain 响应中提取 token 用量

DeepSeek API 在响应中返回 `usage` 字段，LangChain 的 `ChatOpenAI` 将其存入 `AIMessage.response_metadata["token_usage"]`：

```python
# AIMessage.response_metadata 示例
{
    "token_usage": {
        "completion_tokens": 150,
        "prompt_tokens": 800,
        "total_tokens": 950
    },
    "model_name": "deepseek-v4-flash",
    "finish_reason": "stop"
}
```

- [ ] 在 `LLMAdapter` 中新增 `_last_usage` 属性，存储最近一次调用的 token 信息
- [ ] 修改 `chat()`, `chat_template()`, `chat_structured()` 三个方法，调用完成后提取 `response_metadata["token_usage"]`
- [ ] 记录格式：
  ```python
  self._last_usage = {
      "input_tokens": usage["prompt_tokens"],
      "output_tokens": usage["completion_tokens"],
      "total_tokens": usage["total_tokens"],
      "model": self._model_name,
      "timestamp": datetime.now().isoformat(),
  }
  ```

### 1.2 TokenTracker — 汇聚与持久化

**新文件：** `src/core/token_tracker.py`

- [ ] 实现 `class TokenTracker`：
  ```python
  class TokenTracker:
      """Token 消耗追踪器 — 内存汇聚 + 定期刷入 SQLite"""

      def __init__(self, db_path: str = "wiki.db"): ...

      def record(self, operation: str, usage: dict) -> None:
          """记录一次 LLM 调用的 token 消耗

          Args:
              operation: 操作类型（ingest_step1 / ingest_step2 / query / overview）
              usage: 来自 LLMAdapter._last_usage 的字典
          """

      def today_summary(self) -> dict:
          """返回当日汇总：总 tokens、按操作类型分拆、估算费用"""

      def weekly_summary(self) -> dict:
          """返回本周汇总"""

      def flush(self) -> None:
          """将内存中的记录刷入 SQLite"""
  ```

- [ ] SQLite 新增 `token_usage_log` 表（`src/db/schema.py`）：
  ```sql
  CREATE TABLE IF NOT EXISTS token_usage_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      operation TEXT NOT NULL,        -- ingest_step1 / ingest_step2 / query / overview / lint
      input_tokens INTEGER NOT NULL,
      output_tokens INTEGER NOT NULL,
      total_tokens INTEGER NOT NULL,
      model TEXT NOT NULL,
      timestamp TEXT NOT NULL DEFAULT (datetime('now'))
  );
  ```

- [ ] 费用估算：内置 DeepSeek 价格常量（Flash: input ¥1/M, output ¥2/M; Pro: input ¥2.5/M, output ¥8/M）

### 1.3 集成到 WikiCompiler

- [ ] `LLMAdapter` 每次调用后自动将 `_last_usage` 传给 `TokenTracker.record()`
- [ ] 或者在 `LLMAdapter` 内部直接集成 `TokenTracker`（注入模式）：
  ```python
  class LLMAdapter:
      def __init__(self, ..., token_tracker: TokenTracker | None = None):
          self._tracker = token_tracker

      def _record_usage(self, operation: str, response_metadata: dict) -> None:
          if self._tracker and "token_usage" in response_metadata:
              self._tracker.record(operation, response_metadata["token_usage"])
  ```

### 1.4 IngestResponse 增加 token 信息

**文件：** `src/core/models.py`

- [ ] `IngestResponse` 新增可选字段：
  ```python
  class IngestResponse(BaseModel):
      ...
      token_usage: dict[str, int] | None = None
      # {"step1_input": 800, "step1_output": 150, "step2_input": 600, "step2_output": 500, "total": 2050}
  ```

### 验证

- [ ] 执行一次 ingest → `IngestResponse` 中包含 `token_usage` 字段
- [ ] `TokenTracker.today_summary()` 返回合理数据
- [ ] `token_usage_log` 表有记录写入

---

## 第二步：搜索能力补齐

> **背景**：`SearchTool.search()` 和 `WikiRepository.search_pages()` 都是桩代码。
> **目标**：实现基础关键词搜索，为 Query 的"定位候选页面"提供确定性兜底。

**文件：** `src/tools/search_tool.py` + `src/db/repository.py`

### 2.1 SearchTool — 文件名 + 全文关键词

- [ ] 实现 `SearchTool.search(keyword)`：
  1. 遍历 `wiki/` 目录下所有 `.md` 文件
  2. 文件名包含关键词 → 匹配
  3. 文件内容包含关键词 → 匹配（返回匹配行上下文）
  4. 返回 `[{"path": "entities/xxx.md", "title": "XXX", "snippet": "匹配行...", "match_type": "filename/content"}]`

- [ ] 结果按匹配类型排序：文件名匹配 > 标题匹配 > 正文匹配

### 2.2 WikiRepository.search_pages — SQLite 查询

- [ ] 实现 `WikiRepository.search_pages(keyword)`：
  ```python
  def search_pages(self, keyword: str) -> list[dict]:
      conn = self._get_connection()
      rows = conn.execute(
          "SELECT path, title, page_type, tags FROM wiki_pages "
          "WHERE title LIKE ? OR path LIKE ? OR tags LIKE ? "
          "ORDER BY updated_at DESC LIMIT 20",
          (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
      ).fetchall()
      conn.close()
      return [dict(r) for r in rows]
  ```

> ⚠️ Phase 3 只做 SQLite LIKE + 文件名匹配。BM25 / 向量搜索延后到 Phase 5。

### 验证

- [ ] `SearchTool.search("Transformer")` 返回匹配结果
- [ ] `WikiRepository().search_pages("注意力")` 返回匹配页面

---

## 第三步：Query 查询引擎

> **核心设计决策**：Query 不是 RAG 的 chunk 检索，而是**页面级导航查询**。

### 为什么不用 RAG？

| | RAG（检索增强生成） | LLM Wiki Query（导航查询） |
|---|---|---|
| 检索粒度 | 文档 chunk（~500 tokens） | 页面级（完整 Markdown） |
| 检索方式 | 向量相似度 | index.md → wikilinks 遍历 |
| 上下文 | 临时拼接 chunk | 读取完整 wiki 页面 |
| 引用 | 难以追溯 | 精确到 wiki 页面路径 |
| 知识沉淀 | 查询完消失 | 优质答案存档回 wiki |

**面试可讲**："我没有用 RAG。RAG 是'每次检索临时拼凑'，LLM Wiki 是'先编译成结构化知识，再基于页面导航回答'。这就像编译器 vs 解释器的区别。"

### 3.1 Query 流程设计

```
用户提问: "Attention 机制有哪些变体？"
        │
        ▼
Step 1 — 定位候选页面
  ├── 确定性路径: 读取 wiki/index.md → 匹配标题/关键词 → 得到候选页面列表
  ├── 关键词搜索: SearchTool.search("Attention") → 补充候选
  └── 输出: 候选页面路径列表（最多 10 个）
        │
        ▼
Step 2 — 读取 + 扩展
  ├── 读取所有候选页面的内容
  ├── 从每个页面解析 [[wikilinks]] → 读 1 层深度关联页面
  └── 输出: 组装好的上下文（页面内容 + 来源路径）
        │
        ▼
Step 3 — LLM 综合回答
  ├── 系统指令: 你是 Wiki Query Agent
  ├── 输入: 用户问题 + 组装的页面上下文
  ├── 输出格式要求: 答案 + 引用来源（wiki 页面路径）
  └── 输出: 结构化回答
        │
        ▼
Step 4（可选）— 归档
  └── 如果答案质量高 → 写入 wiki/queries/{slug}.md
```

### 3.2 实现 WikiCompiler.query()

**文件：** `src/core/wiki_compiler.py`

- [ ] 实现 `query(question: str) -> dict` 方法：

```python
def query(self, question: str, max_pages: int = 10, archive: bool = False) -> dict:
    """基于页面导航的 Wiki 查询

    Args:
        question: 用户问题
        max_pages: 最多加载的候选页面数
        archive: 是否将答案归档到 wiki/queries/

    Returns:
        {"answer": "...", "sources": ["entities/xxx.md", ...], "archived": "queries/xxx.md"}
    """

    # Step 1: 定位候选页面
    candidates = self._locate_candidates(question, max_pages)

    # Step 2: 读取页面 + 扩展 wikilinks
    context = self._build_context(candidates)

    # Step 3: LLM 综合回答
    answer_data = self._synthesize_answer(question, context)

    # Step 4: 可选归档
    archived = None
    if archive:
        archived = self._archive_query(question, answer_data)

    return {**answer_data, "archived": archived}
```

#### 3.2.1 `_locate_candidates()` — 候选页面定位

```python
def _locate_candidates(self, question: str, limit: int) -> list[str]:
    """混合策略定位候选页面"""
    paths = set()

    # 策略 A: SQLite 标题/标签搜索（确定性）
    for page in self.repo.search_pages(question):
        paths.add(page["path"])
        if len(paths) >= limit:
            return list(paths)

    # 策略 B: 全文关键词搜索
    for result in self.search_tool.search(question):
        paths.add(result["path"])
        if len(paths) >= limit:
            break

    # 策略 C: 如果候选太少，LLM 读 index.md 推荐
    if len(paths) < 3:
        llm_suggestions = self._llm_suggest_pages(question)
        paths.update(llm_suggestions)

    return list(paths)[:limit]
```

#### 3.2.2 Query Prompt

**文件：** `src/llm/prompts.py` — 新增 `SYSTEM_PROMPT_QUERY` 的完整版本

```python
SYSTEM_PROMPT_QUERY = """你是一个 Wiki Query Agent。你的任务是基于 Wiki 知识库的内容回答用户问题。

## 输入

你将收到：
1. 用户的问题
2. 从 Wiki 中检索到的相关页面内容（每个页面标注了来源路径）

## 输出要求

请以 JSON 格式输出（不要用 markdown 代码块包裹）：

{
  "answer": "综合回答的完整 Markdown 文本",
  "sources": ["页面路径1", "页面路径2"],
  "confidence": "high/medium/low",
  "gaps": ["知识库中缺失的信息点"]  // 可选
}

## 回答规范

1. **引用来源**：回答中使用 `[[页面路径|显示名]]` 引用 wiki 页面
2. **诚实标注**：如果知识库中信息不足，明确说"知识库中尚未覆盖…"
3. **置信度**：
   - high — 知识库中有明确、一致的信息
   - medium — 信息存在但有推断成分
   - low — 信息不完整，回答包含较多推测
"""
```

### 验证

- [ ] 对已有 wiki 页面提问 → 返回带 `[[引用]]` 的答案
- [ ] 对不在 wiki 中的主题提问 → 回答中明确标注"知识库尚未覆盖"
- [ ] `sources` 列表中的页面路径确实存在
- [ ] 如果传入 `archive=True` → `wiki/queries/` 下生成新文件

---

## 第四步：API 端点完善

> **背景**：当前 `/wiki` 和 `/wiki/{path}` 返回 HTML 页面（给人类浏览）。
> Phase 3 需要补充 **JSON API**（给程序/AI 调用），以及 Query 和 Usage 端点。

**文件：** `src/main.py`

### 4.1 页面列表 API

- [ ] `GET /v1/pages` — 返回所有 wiki 页面元数据列表（JSON）
  ```python
  @app.get("/v1/pages")
  async def list_pages(type: str | None = None, limit: int = 50, offset: int = 0):
      """列出 Wiki 页面

      Query params:
          type: 按类型过滤（entity / concept / source / query）
          limit: 每页数量（默认 50）
          offset: 偏移量
      """
  ```

  响应示例：
  ```json
  {
    "total": 42,
    "pages": [
      {
        "path": "entities/Transformer.md",
        "title": "Transformer 架构",
        "type": "entity",
        "tags": ["deep-learning", "attention"],
        "word_count": 320,
        "updated_at": "2026-07-07T15:30:00",
        "links_count": 5,
        "backlinks_count": 3
      }
    ]
  }
  ```

### 4.2 页面详情 API（JSON）

- [ ] `GET /v1/pages/{path}` — 返回单个页面的完整内容 + 元数据（JSON）
  ```python
  @app.get("/v1/pages/{page_path:path}")
  async def get_page(page_path: str):
      """获取单个 Wiki 页面的内容（JSON）"""
  ```

  响应示例：
  ```json
  {
    "path": "entities/Transformer.md",
    "title": "Transformer 架构",
    "content": "# Transformer 架构\n\n...",
    "type": "entity",
    "tags": ["deep-learning", "attention"],
    "links": ["concepts/self_attention.md", "entities/Vaswani.md"],
    "backlinks": ["concepts/deep_learning.md"],
    "visibility": "public",
    "created_at": "2026-07-06T10:00:00",
    "updated_at": "2026-07-07T15:30:00"
  }
  ```

- [ ] 对 `visibility: restricted` 的页面 → 返回 `{"status": "locked", "message": "此页面需要密码验证"}`（密码校验本身 Phase 4 实现）

### 4.3 Query API

- [ ] `POST /v1/query` — 查询 Wiki 知识库
  ```python
  @app.post("/v1/query")
  async def query(request: QueryRequest):
      """查询 Wiki 知识库，返回带引用的答案"""
  ```

  请求体：
  ```json
  {
    "question": "什么是 Self-Attention？",
    "archive": true   // 可选：是否归档答案
  }
  ```

  响应体：
  ```json
  {
    "answer": "Self-Attention 是一种...详见 [[concepts/self_attention.md|Self-Attention]]",
    "sources": ["concepts/self_attention.md", "entities/Transformer.md"],
    "confidence": "high",
    "gaps": [],
    "archived": "queries/self-attention-explained.md",
    "token_usage": {"total_tokens": 1200}
  }
  ```

### 4.4 Token 使用量 API

- [ ] `GET /v1/usage` — 查询 token 消耗
  ```python
  @app.get("/v1/usage")
  async def get_usage(period: str = "today"):
      """查询 token 消耗统计

      Query params:
          period: today / week / month
      """
  ```

  响应示例：
  ```json
  {
    "period": "today",
    "total_tokens": 15000,
    "by_operation": {
      "ingest_step1": {"tokens": 5000, "cost_estimate": "¥0.008"},
      "ingest_step2": {"tokens": 8000, "cost_estimate": "¥0.018"},
      "query": {"tokens": 2000, "cost_estimate": "¥0.004"}
    },
    "total_cost_estimate": "¥0.03"
  }
  ```

### 4.5 已有路由整理

| 路由 | 方法 | 状态 | 说明 |
|------|------|------|------|
| `/` | GET | ✅ 已有 | 服务运行状态 |
| `/health` | GET | ✅ 已有 | 健康检查 |
| `/wiki` | GET | ✅ 已有 | HTML 浏览首页 |
| `/wiki/{path}` | GET | ✅ 已有 | HTML 页面渲染 |
| `/v1/ingest` | POST | ✅ 已有 | 摄入源文件 |
| `/v1/query` | POST | ⬜ 新增 | Wiki 查询（JSON） |
| `/v1/pages` | GET | ⬜ 新增 | 页面列表（JSON） |
| `/v1/pages/{path}` | GET | ⬜ 新增 | 页面详情（JSON） |
| `/v1/usage` | GET | ⬜ 新增 | Token 消耗统计 |
| `/v1/privacy/rules` | GET | ✅ 已有 | 隐私规则列表 |
| `/v1/privacy/rules` | POST | ✅ 已有 | 添加隐私规则 |
| `/v1/privacy/rules/{kw}` | DELETE | ✅ 已有 | 删除隐私规则 |
| `/v1/lint` | GET | ⬜ Phase 4 | Wiki 健康检查 |
| `/docs` | GET | ✅ 自动 | Swagger 文档 |

### 验证

- [ ] `GET /v1/pages` 返回正确数量和字段
- [ ] `GET /v1/pages?type=entity` 只返回实体页
- [ ] `GET /v1/pages/concepts/xxx.md` 返回完整 JSON
- [ ] `POST /v1/query {"question": "..." }` 返回带引用的回答
- [ ] `GET /v1/usage` 返回 token 统计

---

## 第五步：答案归档

> **核心理念**：好的问答不应该淹没在聊天记录中。LLM Wiki 的一个核心优势是"知识越用越厚"——每一次好的 Query 都让 wiki 更丰富。

**文件：** `src/core/wiki_compiler.py`

### 5.1 `_archive_query()` 实现

- [ ] 实现答案归档方法：
  ```python
  def _archive_query(self, question: str, answer_data: dict) -> str | None:
      """将查询结果归档到 wiki/queries/

      归档条件：LLM 置信度 >= medium 且答案非空
      """
      if not answer_data.get("answer"):
          return None
      if answer_data.get("confidence") == "low":
          return None

      # 生成文件名（取问题前 30 字的 slug）
      slug = self._question_to_slug(question)
      path = f"queries/{slug}.md"

      # 组装归档内容
      content = f"""---
title: "{question}"
type: query
created: {self._today()}
tags: [query]
sources: {answer_data.get("sources", [])}
confidence: {answer_data.get("confidence", "medium")}
---

# {question}

{answer_data["answer"]}

## 来源

""" + "\n".join(f"- [[{s}]]" for s in answer_data.get("sources", []))

      self.writer.write_page(path, content)
      self.repo.add_page(path=path, title=question, page_type="query",
                         tags=["query"], word_count=len(content))

      # 更新 index（新页面加入）
      self._update_index()

      return path
  ```

- [ ] 用户可通过 `archive: false` 跳过归档

### 验证

- [ ] 一次置信度 high 的 Query → `wiki/queries/` 下生成对应 `.md` 文件
- [ ] 归档文件包含 YAML frontmatter 和 `[[来源链接]]`
- [ ] index.md 自动更新，包含新归档的 queries 页面

---

## 第六步：Phase 2 遗留项收尾

> 这些是 Phase 2 设计了但没完全实现的功能，Phase 3 开局快速收掉。

### 6.1 WikiRepository 补齐

- [ ] 实现 `get_orphan_pages()` — 找出无入链的页面
  ```sql
  SELECT path FROM wiki_pages
  WHERE path NOT IN (SELECT DISTINCT target_path FROM page_links)
  ```

- [ ] 实现 `search_pages()` — 已在第二步中完成

### 6.2 SearchTool 补齐

- [ ] 实现 `SearchTool.search()` — 已在第二步中完成

### 6.3 index.md 上下文缩减（Token 优化）

> 来自 `notes/token-cost-optimization.md` 建议 #3

- [ ] 新增 `_index_summary()` 方法（替代直接传完整 index.md）：
  ```python
  def _index_summary(self) -> str:
      """返回 index.md 的摘要（~500 tokens），用于 Step 1 上下文"""
      import sqlite3
      conn = sqlite3.connect(self.repo.db_path)
      conn.row_factory = sqlite3.Row

      total = conn.execute("SELECT COUNT(*) as n FROM wiki_pages").fetchone()["n"]
      by_type = conn.execute(
          "SELECT page_type, COUNT(*) as n FROM wiki_pages GROUP BY page_type"
      ).fetchall()
      recent = conn.execute(
          "SELECT path, title FROM wiki_pages ORDER BY updated_at DESC LIMIT 10"
      ).fetchall()
      conn.close()

      lines = [
          f"Wiki 总页面数：{total}",
          "按类型分布：" + ", ".join(f"{r['page_type']}: {r['n']}" for r in by_type),
          "最近更新的页面：",
      ]
      for r in recent:
          lines.append(f"  - {r['path']} — {r['title']}")

      return "\n".join(lines)
  ```

- [ ] 在 `ingest()` Step 1 中用 `_index_summary()` 替代 `_get_index_context()`（后者返回完整 index.md，可能 3000+ tokens）

### 验证

- [ ] `_index_summary()` 输出 < 800 字符
- [ ] ingest 流程仍正常工作

---

## 本阶段 LangChain 学习重点

| 概念 | 用于什么 | 优先级 |
|------|---------|--------|
| `AIMessage.response_metadata` | 提取 token 用量 | 🔴 必学 |
| `StrOutputParser` | Query 回答的纯文本解析 | 🟡 推荐 |
| `RunnableSequence` | Query 的定位→读取→综合链式编排 | 🟢 可选 |

> 详见 [knowledge-reference.md](knowledge-reference.md) 第 16 节。

---

## 交付物

Phase 3 完成时：

- [ ] `POST /v1/query` 返回基于 wiki 页面的综合回答（带 `[[引用]]`）
- [ ] `GET /v1/pages` 和 `GET /v1/pages/{path}` JSON API 可用
- [ ] `GET /v1/usage` 返回当日/本周 token 消耗与费用估算
- [ ] `SearchTool.search()` 实现文件名+关键词搜索
- [ ] `WikiRepository.search_pages()` 实现 SQLite 查询
- [ ] 每次 `IngestResponse` 包含 `token_usage` 字段
- [ ] 高质量 Query 答案自动归档到 `wiki/queries/`
- [ ] Step 1 上下文从完整 index.md 缩减为摘要（~500 tokens）
- [ ] `pytest` 新测试覆盖 query、search、token_tracker
- [ ] 日 token 消耗可监控、可追溯（`token_usage_log` 表）

---

## 验证标准（端到端）

```bash
# 1. Token 追踪生效
curl -X POST http://localhost:8000/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"source_path": "sources/test.md"}'
# → 响应中包含 "token_usage": {...}

# 2. 查询 token 消耗
curl http://localhost:8000/v1/usage
# → {"total_tokens": 15000, "total_cost_estimate": "¥0.03", ...}

# 3. 搜索页面
curl "http://localhost:8000/v1/pages?type=concept&limit=10"
# → {"total": 18, "pages": [...]}

# 4. 页面详情
curl http://localhost:8000/v1/pages/concepts/self_attention.md
# → {"path": "...", "content": "...", "links": [...], ...}

# 5. Query 查询
curl -X POST http://localhost:8000/v1/query \
  -H "Content-Type: application/json" \
  -d '{"question": "什么是 Self-Attention？", "archive": true}'
# → {"answer": "...", "sources": ["..."], "confidence": "high"}

# 6. 答案归档
ls wiki/queries/
# → self-attention-explained.md 存在

# 7. Wiki 浏览（已有，确认不受影响）
curl http://localhost:8000/wiki
# → HTML 首页正常

# 8. API 文档
curl http://localhost:8000/docs
# → Swagger 列出所有新端点
```

---

## 预估时间

| 步骤 | 内容 | 预估天数 |
|------|------|---------|
| 第一步 | Token 追踪基础设施 | 1-2 天 |
| 第二步 | 搜索能力补齐 | 1 天 |
| 第三步 | Query 查询引擎（核心） | 2-3 天 |
| 第四步 | API 端点完善 | 1-2 天 |
| 第五步 | 答案归档 | 1 天 |
| 第六步 | Phase 2 遗留收尾 | 1 天 |
| **合计** | | **7-10 天** |

> Phase 3 是功能密集阶段——完成后你有了完整的 "Ingest → Query → 归档" 闭环，可以开始邀请别人试用。
