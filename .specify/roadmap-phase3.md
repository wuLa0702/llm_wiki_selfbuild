# Phase 3 — Query 查询 + Token 治理 + API 完善

> **状态**：⬜ 未开始
> **对标**：nashsu v0.3 / cobusgreyling v0.2
> **前置**：Phase 2 完成（两步 CoT + 缓存 + 导航文件 + 隐私标记）
>
> 完整路线图：[roadmap.md](roadmap.md)

---

## 目标

Phase 1-2 完成了"写"的能力，Phase 3 聚焦"读"：

- wiki 写进去了，要能**查出来**——实现基于 wikilinks 图扩展的导航式 Query（非 RAG）
- 知道每次操作**花了多少 tokens**——Token 治理透明化
- 知识图谱的**确定性基础**——正则解析 wikilinks 构建图结构（零 LLM 成本）
- 基本的**自诊断能力**——断链检测 + 孤页检测（零 LLM 成本）
- API 体系补全——JSON 格式的页面列表/详情/搜索 API

### 🎯 自检对标

> **对照 nashsu v0.3.13 和 cobusgreyling v0.2.1 的实际功能后，修正了 Phase 3 范围。**
>
> 两个参考项目在 v0.2-v0.3 阶段都已有：wikilinks 图解析 + 基础静态 lint。
> 这些都是**确定性算法（零 LLM 成本）**，不应延后到 Phase 4。
>
> 修正：Phase 3 新增 **第三步（Wikilinks 图解析器）** 和 **第五步（静态 Lint 检查）**。
> 详见 [roadmap-phase3-selfcheck.md](roadmap-phase3-selfcheck.md) 完整自检报告。

---

## 依赖链

```
Phase 2 产物（CoT ingest + 缓存 + 导航文件 + index.md + wiki/ *.md）
        │
        ▼
第一步：Token 使用量追踪          ← src/llm/adapter.py + src/core/token_tracker.py（基础设施）
        │
        ▼
第二步：搜索能力补齐              ← src/tools/search_tool.py + src/db/repository.py
        │
        ▼
第三步：Wikilinks 图解析器        ← src/core/graph.py（新文件）— 确定性解析，零 LLM 成本
        │
        ▼
第四步：Query 查询引擎            ← src/core/wiki_compiler.py（核心功能：图扩展 + 导航查询）
        │
        ▼
第五步：静态 Lint 检查            ← src/core/linter.py（新文件）— 断链/孤页/索引缺失，零 LLM 成本
        │
        ▼
第六步：API 端点完善              ← src/main.py（对外接口）
        │
        ▼
第七步：答案归档                  ← src/core/wiki_compiler.py（知识沉淀）
        │
        ▼
第八步：Source 自动监听 🆕          ← src/core/watcher.py（新文件）— 轮询 raw/sources/，零 LLM 成本
        │
        ▼
第九步：Phase 2 遗留收尾            ← index.md 上下文缩减 + 补全桩代码

并行支线（可随时启动，不阻塞主干）:
  Source 自动监听 ← 依赖 ingest() 已可用 → 第一步之后即可开始
```

**关键依赖**：
- 第三步（图解析）→ 第四步（Query 图扩展）→ **Query 的质量依赖图结构**
- 第三步（图解析）→ 第五步（Lint 断链检测）→ **Lint 复用同一份图数据**
- 第一步（Token 追踪）必须最先做 → 后续每步都能看到 LLM 调用成本

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

## 第三步：Wikilinks 图解析器

> **自检修正**：这是对 nashsu v0.3 / cobusgreyling v0.2 自检后新增的步骤。
> **核心理由**：wikilinks 解析是**纯正则匹配**（零 LLM 成本），两个参考项目在 v0.2-v0.3 阶段都已实现。
> 它为 Query（图扩展找相关页面）和 Lint（断链检测）提供基础数据。

**新文件：** `src/core/graph.py`

### 3.1 Wikilinks 解析 — 确定性

- [ ] 实现 `parse_wikilinks(content: str) -> list[str]`：
  ```python
  import re

  WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+?)(?:[|#][^\]]+)?\]\]")

  def parse_wikilinks(content: str) -> list[str]:
      """从 Markdown 文本中提取所有 [[wikilinks]] 目标路径"""
      return [m.strip() for m in WIKILINK_PATTERN.findall(content)]
  ```

### 3.2 WikiGraph — 内存图结构

- [ ] 实现 `class WikiGraph`：
  ```python
  class WikiGraph:
      """Wiki 页面的有向图结构（邻接表）"""

      def __init__(self, wiki_dir: str = "wiki"): ...

      def build(self) -> None:
          """遍历 wiki/*.md → 解析 wikilinks → 构建邻接表"""

      def nodes(self) -> list[str]:
          """返回所有节点（页面路径）"""

      def edges(self) -> list[tuple[str, str]]:
          """返回所有有向边 (source → target)"""

      def neighbors(self, path: str, depth: int = 1) -> list[str]:
          """返回 depth 跳内的邻居页面（BFS）"""

      def backlinks(self, path: str) -> list[str]:
          """返回反向链接（哪些页面指向了 path）"""

      def degree(self, path: str) -> dict:
          """返回 {in_degree, out_degree}"""
  ```

- [ ] `build()` 实现细节：
  1. 遍历 `wiki/` 下所有 `.md` 文件
  2. 对每个文件调用 `parse_wikilinks(content)` 提取链接目标
  3. 构建邻接表：`{source_path: [target_paths]}`
  4. 同时计算反向链接索引：`{target_path: [source_paths]}`
  5. 统计每个节点的入度/出度

- [ ] 性能：1000 页以内 < 100ms（纯正则，无 LLM 调用）

### 3.3 集成到 WikiCompiler

- [ ] `WikiCompiler.__init__()` 中初始化 `self.graph = WikiGraph()`
- [ ] 每次 `ingest()` 完成后调用 `self.graph.build()` 重建图
- [ ] `WikiCompiler.query()` 用 `self.graph.neighbors()` 扩展候选页面

### 验证

- [ ] `WikiGraph.build()` 在 100 页 wiki 下正确构建邻接表
- [ ] `neighbors("entities/Transformer.md", depth=1)` 返回直接关联页面
- [ ] `neighbors("entities/Transformer.md", depth=2)` 返回二跳关联
- [ ] `backlinks("concepts/self_attention.md")` 返回所有引用该页面的页面
- [ ] ingest 后图自动刷新

---

## 第四步：Query 查询引擎

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

### 4.1 Query 流程设计（修正：图扩展版）

```
用户提问: "Attention 机制有哪些变体？"
        │
        ▼
Step 1 — 定位候选页面（混合策略）
  ├── 确定性: 读 wiki/index.md → 匹配标题/关键词 → 候选页面列表
  ├── 关键词: SearchTool.search("Attention") → 补充候选
  ├── 图扩展: WikiGraph.neighbors(候选页, depth=2) → 发现不包含关键词但被链接的页面
  └── 输出: 候选页面路径列表（最多 15 个，去重）
        │
        ▼
Step 2 — 读取 + 排序
  ├── 读取所有候选页面的内容
  ├── 按相关性排序：标题精确匹配 > wikilinks 度 > 关键词命中
  └── 取 top-10 页面作为上下文
        │
        ▼
Step 3 — LLM 综合回答
  ├── 系统指令: SYSTEM_PROMPT_QUERY
  ├── 输入: 用户问题 + 组装的页面上下文（标注来源路径）
  ├── 输出格式: JSON { answer, sources, confidence, gaps }
  └── 输出: 结构化回答
        │
        ▼
Step 4（可选）— 归档
  └── 如果答案质量高 → 写入 wiki/queries/{slug}.md
```

> **与初版设计的关键差异**：Step 1 增加了**图扩展**——不仅靠关键词匹配，还能通过 wikilinks 关联找到"不包含关键词但被关联指向"的页面。这正是 LLM Wiki 比 RAG 强的地方：知识之间的连接已经编译好了。

### 4.2 实现 WikiCompiler.query()

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

#### 4.2.1 `_locate_candidates()` — 候选页面定位（修正：三角定位）

```python
def _locate_candidates(self, question: str, limit: int) -> list[str]:
    """混合策略定位候选页面：关键词 + 图扩展 + LLM 兜底"""
    paths: set[str] = set()

    # 策略 A: SQLite 标题/标签搜索（确定性，最快）
    for page in self.repo.search_pages(question):
        paths.add(page["path"])
        if len(paths) >= limit:
            return list(paths)

    # 策略 B: 全文关键词搜索
    for result in self.search_tool.search(question):
        paths.add(result["path"])

    # 策略 C: WikiGraph 扩展（新增！）
    # 对已找到的候选页，通过 wikilinks 图发现"不包含关键词但被关联指向"的页面
    expanded: set[str] = set()
    for p in list(paths):
        expanded.update(self.graph.neighbors(p, depth=1))
    paths.update(expanded)

    # 策略 D: 如果候选太少，LLM 读 index.md 推荐
    if len(paths) < 3:
        llm_suggestions = self._llm_suggest_pages(question)
        paths.update(llm_suggestions)

    return list(paths)[:limit]
```

#### 4.2.2 Query Prompt

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

## 第五步：静态 Lint 检查

> **自检修正**：cobusgreyling v0.2 已有 `lint --skip-llm` 做断链/孤页/索引缺失检测。
> 这些都是**确定性算法（零 LLM 成本）**，Phase 3 就应该做。
> LLM 语义 Lint（矛盾检测、知识缺口识别）延后到 Phase 4。

**新文件：** `src/core/linter.py`

### 5.1 LintTool — 纯静态检测

- [ ] 实现 `class LintTool`：
  ```python
  class LintTool:
      """Wiki 页面健康检查器 — Phase 3 只做确定性检测"""

      def __init__(self, wiki_dir: str = "wiki"): ...

      def check_broken_links(self) -> list[dict]:
          """
          检测断链：[[target]] 指向不存在的文件

          Returns:
              [{"source_page": "entities/xxx.md", "broken_target": "entities/nonexistent.md"}]
          """

      def check_orphan_pages(self) -> list[str]:
          """
          检测孤页：没有任何页面链接到它（0 入链）

          排除 index.md, overview.md, log.md 等导航页面
          """

      def check_index_gaps(self) -> list[str]:
          """
          检测 index.md 中缺失的页面：wiki/ 下存在但 index.md 未列出的页面
          """

      def run_all(self) -> dict:
          """
          运行全部静态检查

          Returns:
              {
                  "broken_links": [...],
                  "broken_links_count": 3,
                  "orphan_pages": [...],
                  "orphan_pages_count": 1,
                  "index_gaps": [...],
                  "index_gaps_count": 2,
                  "health_score": 85  # 0-100，简单加权计算
              }
          """
  ```

- [ ] 断链检测实现：
  1. 用 `WikiGraph.build()` 的 edges 数据
  2. 所有 target 不在 `WikiGraph.nodes()` 中的 → 断链
  3. 跳过 HTTP URL（`http://` / `https://` 开头的链接）

- [ ] 孤页检测实现：
  1. 用 `WikiGraph.backlinks()` 数据
  2. 入度为 0 且不在排除列表（index.md, overview.md, log.md）中的页面 → 孤页

### 5.2 集成到 WikiCompiler

- [ ] 实现 `WikiCompiler.lint()` 方法：
  ```python
  def lint(self) -> dict:
      """运行静态 Lint 检查（Phase 3 只做确定性检测）"""
      linter = LintTool(wiki_dir=self.writer.base_dir)
      return linter.run_all()
  ```

- [ ] 在 `ingest()` 完成后可选触发 lint（如果检测到断链/孤页，记录 warning 日志）

### 5.3 健康评分

```
health_score = 100
  - 每个断链: -5 分
  - 每个孤页: -10 分
  - 每个 index 缺失: -3 分
最低 0 分
```

### 验证

- [ ] 创建一个含断链的 wiki 页面 → `check_broken_links()` 检出
- [ ] 创建一个孤页（无入链） → `check_orphan_pages()` 检出
- [ ] `run_all()` 返回完整报告含健康评分
- [ ] 零 LLM 调用（纯确定性算法）

---

## 第六步：API 端点完善

> **背景**：当前 `/wiki` 和 `/wiki/{path}` 返回 HTML 页面（给人类浏览）。
> Phase 3 需要补充 **JSON API**（给程序/AI 调用），以及 Query 和 Usage 端点。

**文件：** `src/main.py`

### 6.1 页面列表 API

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

### 6.2 页面详情 API（JSON）

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

### 6.3 Query API

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

### 6.4 Token 使用量 API

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

### 6.5 Lint API

- [ ] `GET /v1/lint` — 运行静态 Lint 检查
  ```python
  @app.get("/v1/lint")
  async def lint():
      """运行 Wiki 健康检查（静态 — 断链 + 孤页 + 索引缺失）"""
  ```

  响应示例：
  ```json
  {
    "broken_links": [
      {"source_page": "entities/xxx.md", "broken_target": "entities/nonexistent.md"}
    ],
    "broken_links_count": 3,
    "orphan_pages": ["concepts/forgotten.md"],
    "orphan_pages_count": 1,
    "index_gaps": ["entities/new_page.md"],
    "index_gaps_count": 1,
    "health_score": 75
  }
  ```

### 6.6 已有路由整理

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
| `/v1/lint` | GET | ⬜ 新增 | Wiki 健康检查（静态） |
| `/v1/lint?semantic=true` | GET | ⬜ Phase 4 | 语义 Lint（LLM 矛盾检测） |
| `/v1/watcher/start` | POST | ⬜ 新增 | 启动 Source 监听 |
| `/v1/watcher/stop` | POST | ⬜ 新增 | 停止 Source 监听 |
| `/v1/watcher/status` | GET | ⬜ 新增 | 查询监听状态 |
| `/docs` | GET | ✅ 自动 | Swagger 文档 |

### 验证

- [ ] `GET /v1/pages` 返回正确数量和字段
- [ ] `GET /v1/pages?type=entity` 只返回实体页
- [ ] `GET /v1/pages/concepts/xxx.md` 返回完整 JSON
- [ ] `POST /v1/query {"question": "..." }` 返回带引用的回答
- [ ] `GET /v1/usage` 返回 token 统计

---

## 第七步：答案归档

> **核心理念**：好的问答不应该淹没在聊天记录中。LLM Wiki 的一个核心优势是"知识越用越厚"——每一次好的 Query 都让 wiki 更丰富。

**文件：** `src/core/wiki_compiler.py`

### 7.1 `_archive_query()` 实现

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

## 第八步：Source 文件夹自动监听 🆕

> **背景**：当前 ingest 必须手动调用 `POST /v1/ingest`。实际使用中，你应该是"丢文件到 raw/sources/ → 自动处理"。
> **来源**：对标 nashsu/llm_wiki 的 "Source 文件夹自动监听" 功能。
> **成本**：文件系统轮询 / watchdog 库，零 LLM 调用。

**新文件：** `src/core/watcher.py`

### 8.1 SourceWatcher — 基础版（轮询）

- [ ] 实现 `class SourceWatcher`：
  ```python
  class SourceWatcher:
      """监听 raw/sources/ 目录的文件变更，自动触发 ingest"""

      def __init__(self, sources_dir: str = "raw/sources", poll_interval: int = 10): ...

      def start(self) -> None:
          """启动后台轮询线程"""

      def stop(self) -> None:
          """停止轮询"""

      def status(self) -> dict:
          """返回监听状态：{running, watched_dir, poll_interval, last_check, files_processed}"""

      def _scan_and_ingest(self) -> None:
          """扫描目录 → 发现新文件 → 调用 WikiCompiler.ingest()"""
  ```

- [ ] 扫描逻辑：
  1. 列出 `raw/sources/` 下所有文件（排除 `.gitkeep` 等隐藏文件）
  2. 对比已处理文件集合（内存 set + SQLite `ingest_cache` 表兜底）
  3. 新文件 → 记录到待处理队列 → 串行调用 `WikiCompiler.ingest()`
  4. 处理完毕 → 加入已处理集合

- [ ] 基础版范围（Phase 3）：
  - ✅ 检测新文件 → 自动 ingest
  - ✅ 启动/停止/状态查询
  - ✅ 通过 API 控制
  - ❌ 检测文件删除 → 延后到 Phase 6
  - ❌ 检测文件修改 → 延后到 Phase 6（SHA256 缓存已能防止重复处理）

### 8.2 API 端点

- [ ] `POST /v1/watcher/start` — 启动监听
  ```json
  {"status": "started", "watching": "raw/sources/", "poll_interval": 10}
  ```

- [ ] `POST /v1/watcher/stop` — 停止监听

- [ ] `GET /v1/watcher/status` — 查询监听状态
  ```json
  {
    "running": true,
    "watched_dir": "raw/sources/",
    "poll_interval_seconds": 10,
    "last_check": "2026-07-07T15:30:00",
    "files_processed": 5
  }
  ```

### 8.3 启动时自动开启

- [ ] FastAPI `@app.on_event("startup")` 中自动启动 SourceWatcher（可通过环境变量 `WATCHER_ENABLED=false` 关闭）
- [ ] 开发调试时可以关闭（避免每次启动都触发 ingest）

### 验证

- [ ] 启动服务 → 丢一个 `.md` 文件到 `raw/sources/` → 10 秒内自动触发 ingest
- [ ] `GET /v1/watcher/status` 返回 files_processed 增加
- [ ] 已缓存的文件不会被重复处理（SHA256 命中 → skip）
- [ ] `POST /v1/watcher/stop` → 丢文件 → 不触发 ingest

---

## 第九步：Phase 2 遗留项收尾

> 这些是 Phase 2 设计了但没完全实现的功能，Phase 3 开局快速收掉。

### 9.1 WikiRepository 补齐（大部分已由前序步骤覆盖）

- [x] `search_pages()` — ✅ 第二步已完成
- [x] `get_orphan_pages()` — ✅ 第五步 `LintTool.check_orphan_pages()` 已覆盖
  （等价 SQL：`SELECT path FROM wiki_pages WHERE path NOT IN (SELECT DISTINCT target_path FROM page_links)`）

### 9.2 SearchTool 补齐

- [ ] 实现 `SearchTool.search()` — 已在第二步中完成

### 9.3 index.md 上下文缩减（Token 优化）

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

- [ ] `WikiGraph` 解析 `[[wikilinks]]` 构建有向图（邻接表 + 反链索引）
- [ ] `POST /v1/query` 返回基于 wikilinks 图扩展的综合回答（带 `[[引用]]`）
- [ ] `GET /v1/pages` 和 `GET /v1/pages/{path}` JSON API 可用
- [ ] `GET /v1/lint` 返回静态健康检查报告（断链 + 孤页 + 索引缺失 + 健康评分）
- [ ] `GET /v1/usage` 返回当日/本周 token 消耗与费用估算
- [ ] `SearchTool.search()` 实现文件名+关键词搜索
- [ ] `WikiRepository.search_pages()` 实现 SQLite 查询
- [ ] 每次 `IngestResponse` 包含 `token_usage` 字段
- [ ] 高质量 Query 答案自动归档到 `wiki/queries/`
- [ ] Step 1 上下文从完整 index.md 缩减为摘要（~500 tokens）
- [ ] `SourceWatcher` 自动监听 raw/sources/ 新文件 → 自动 ingest
- [ ] `pytest` 新测试覆盖 query、search、graph、linter、watcher、token_tracker
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
| 第三步 | Wikilinks 图解析器 | 1-2 天 |
| 第四步 | Query 查询引擎（核心） | 2-3 天 |
| 第五步 | 静态 Lint 检查 | 1 天 |
| 第六步 | API 端点完善 | 1-2 天 |
| 第七步 | 答案归档 | 1 天 |
| 第八步 | Source 自动监听 🆕 | 1 天 |
| 第九步 | Phase 2 遗留收尾 | 1 天 |
| **合计** | | **10-15 天** |

> 自检后新增图解析器 + 静态 Lint + Source 监听（均为确定性算法，零 LLM 成本）。
> Phase 3 是功能密集阶段——完成后你有了完整的 "丢文件→自动处理→查询→Lint→归档" 闭环。
