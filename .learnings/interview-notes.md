# 面试复盘笔记

> 按时间倒序，记录开发中遇到的问题、讨论过程和解决方案。

---

## 2026-07-15：Wikilink 路径规范

### 问题

LLM 生成 wikilink 时使用裸名（`[[毕木]]`），而断链检测用完整路径匹配（`entities/毕木.md`），导致 165 个断链，包括大量有效链接误报。

### 讨论

- 模糊匹配方案：去掉 `.md` 扩展名和目录前缀再对比 → 同名冲突风险（`concepts/专注.md` vs `entities/专注.md`）
- 源头方案：要求 LLM 生成完整路径 → 精确匹配，不改 lint 逻辑

### 方案

选择源头方案——修改 `SYSTEM_PROMPT_INGEST_GENERATE`，新增 Wikilink 规范：强制使用 `[[目录/文件名.md]]` 完整路径，禁止裸名。

### 代码

`src/llm/prompts.py` — `SYSTEM_PROMPT_INGEST_GENERATE` 新增 Wikilink 规范块。

---

## 2026-07-15：frontmatter 排版异常 + 断链逻辑 + LLM 超时

### 问题

导入 感想随笔2024.md 后，wiki 页面出现三个问题：
1. 页面排版古怪——frontmatter YAML 原样出现在正文顶部
2. 大量红色"断链"（165个）
3. 页面内容中 wikilink 跳转失败

### 分析

**frontmatter 排版**：LLM 生成的 .md 文件包含 YAML frontmatter（`--- ... ---`），Python 的 `markdown.markdown()` 不解析 frontmatter，将其作为普通文本渲染，导致 `title: "饭饭" type: entity ...` 显示在正文中。

**断链根因**：lint 的 `check_broken_links` 用 `graph.nodes()` 对比 wikilink 目标，节点是完整文件路径（`entities/饭饭.md`），但 LLM 生成的是裸名（`[[毕木]]`），格式不匹配导致误报。另一部分是 LLM 虚构的链接（`[[大饼]]`），源文件中不存在此页面。

**LLM 超时**：`adapter.py` 中 `timeout=15` + `max_retries=1`，大文件 Step 2 生成页面耗时 >15s，两轮重试共 30s 就放弃了。改为 `timeout=120` + `max_retries=0` 后成功。

### 方案

**frontmatter**：比较了四种方案（正则剥离 / python-frontmatter / DB 存 frontmatter / 纯渲染层），推荐 `python-frontmatter` 库——4KB 纯 Python，正确处理 YAML 语法，零外部依赖。

**断链**：分类处理。格式不匹配 → 改 lint 匹配逻辑（模糊匹配 + 去扩展名）；LLM 虚构 → 保留一键修复但应先区分再清理。

**一键修复的副作用**：`POST /v1/lint/fix` 删除了全部 165 个 wikilink，包括格式不匹配的有效链接（如 `[[毕木]]` 指向存在的 `entities/毕木.md`）。误杀了本该保留的内容。

### page_links 检查方法

```
graph.nodes() 返回 wiki/ 下所有 .md 文件路径
check_broken_links 遍历所有 edge (source→target wikilink)
对比 target 是否在 nodes 集合中 → 不在 = 报断链
```

### 相关代码

- `src/core/lint/linter.py:70` — `check_broken_links()`
- `src/llm/adapter.py:97` — `timeout=15, max_retries=1`
- `src/core/compiler/wiki_compiler.py:519` — Step 1 prompt 注入
- `src/api/routes/lint.py:14` — `POST /v1/lint/fix`

---

## 2026-07-15：wiki-schema.md 融入 LLM 管线

### 背景

`purpose.md`（知识方向）已通过 `_get_purpose_context()` 注入 Step 1 prompt，但 `wiki-schema.md`（页面规范）未接入。

### 改动

`wiki_compiler.py` 新增 `_get_schema_context()`，读取 `wiki/wiki-schema.md`，和 `purpose_context` 一起注入 Step 1 分析 prompt。LLM 在分析源文件时就能看到：7 种页面类型、命名规范、frontmatter 字段、交叉引用规则。

### 模板与运行时副本

- 代码模板：`src/templates/purpose.md.default`、`src/templates/wiki-schema.md.default`
- 运行时副本：根目录 `purpose.md`、`wiki/wiki-schema.md`
- 重置按钮：`POST /v1/system/reset` 清空所有数据 + 重新生成模板

### 增量 vs 全量

schema 改 → 只对新 ingest 生效。已有 24 个页面保持原格式不动。用户如需统一旧页面，手动触发单页重新生成。

---

## 2026-07-15：LLM 超时修复

### 问题

导入 67KB 源文件，Step 2 调用 LLM 生成页面时超时。

### 根因

`adapter.py:97` — LangChain 的 `ChatOpenAI(timeout=15, max_retries=1)`。单次调用 15s 超时 + 重试 1 次 = 总共 30s。大 prompt 的生成调用需要 >15s。

### 修复

`timeout=15 → 120, max_retries=1 → 0`。一次最长等 2 分钟，不重试。

### 结果

感想随笔2024.md (52KB) → 24 个 Wiki 页面，一次成功无超时。

---

## 2026-07-15：异步导入响应模型不匹配

### 问题

`/v1/ingest/folder` 的 async 模式返回 `enqueued/n` 但路由声明了 `response_model=FolderImportResponse`（含 `success/created`），导致前端看到 `success: 0`。

### 修复

去除 response_model，async 路径直接返回 `JSONResponse(content=result)`。

### 涉及文件

`src/api/routes/ingest.py:78`

---

## 2026-07-15：断链修复——三层策略（建议修正→存根→补充）

### 背景

原有 `POST /v1/lint/fix` 直接删除所有断链 wikilink，误杀有效链接。参考项目使用模糊匹配、存根创建、孤页补反链的三层修复，而非删除。

### 决策

- **格式修复（裸名→完整路径）**：自动——`auto_fix_wikilinks()` 在导入后同步执行
- **模糊修正 + 存根 + 缺链补充**：手动——`POST /v1/lint/fix`
- 用户调用，而非自动，参考项目的做法

### 策略详情

策略1（建议修正）：difflib.SequenceMatcher 模糊匹配(threshold=0.5)，匹配到已有页面则重写 `[[target]]`。  
策略2（创建存根）：无匹配时为断链创建 type:query 占位页，保留原链接。  
策略3（补充缺失）：入链=0 的页面，在同类最相关页面尾部追加 wikilink。

### 代码

- `linter.py`：`auto_fix_wikilinks()`, `suggest_correction()`, `create_stub()`, `fill_missing_links()`
- `lint.py`：`POST /v1/lint/fix` 返回 `{rewritten, stubs, filled}`
- `importer.py`：导入完成自动调 `auto_fix_wikilinks()`，返回 `wikilinks_fixed`
