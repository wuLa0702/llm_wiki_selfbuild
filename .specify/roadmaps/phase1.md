# Phase 1 MVP — 实现路线图

> 📌 **注意**：完整开发路线图已移至 [roadmap.md](roadmap.md)，包含 Phase 1-5 全部阶段。
> 本文档保留 Phase 1 的详细任务分解，作为日常开发参考。

> 目标：从原始素材（raw/）"编译"为结构化 Wiki 页面（wiki/），完成 Ingest 端到端流程。

## 依赖链

```
LLMAdapter ← WikiCompiler → ReadTool / WriteTool / WikiRepository
                                      ↑
                                 main.py (API)
```

底层先实现，上层后实现。**从下往上，逐层验证。**

---

## 第一步：LLM 调用

**文件：** `src/llm/adapter.py`

- [ ] 实现 `chat(prompt, system_prompt) → str`
  - 读取 `.env` 配置（`DEEPSEEK_API_KEY`、`DEEPSEEK_API_BASE`、`DEEPSEEK_MODEL`）
  - 通过 LangChain 调用 DeepSeek API
  - 加 `timeout` 和 `max_retries`
- [ ] 实现 `chat_structured(prompt, schema) → dict`（可选，可延后）
- [ ] 验证：本地可调通

**环境变量已配置：**
```
DEEPSEEK_API_KEY=<your-api-key>
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
LLM_PROVIDER=deepseek
```

---

## 第二步：工具能读写

### ReadTool

**文件：** `src/tools/read_tool.py`

- [ ] 实现 `read_file(filename) → str`
  - 路径前缀校验：只能读 `raw/`
  - 拒绝路径穿越（`../`）
  - 文件不存在时抛明确异常
- [ ] 实现 `list_directory(directory) → list[str]`
  - 同上权限校验

### WriteTool

**文件：** `src/tools/write_tool.py`

- [ ] 实现 `write_page(relative_path, content) → str`
  - 路径前缀校验：只能写 `wiki/`
  - 拒绝路径穿越
  - 自动创建中间目录
  - 返回写入的完整路径

---

## 第三步：数据库能存

**文件：** `src/db/repository.py`

**表结构：** `src/db/schema.py`（已就绪，无需修改）

- [ ] 实现 `add_page(path, title, page_type, tags)`
  - UPSERT 语义（存在则更新）
- [ ] 实现 `add_link(source, target)`
  - 记录页面间双向链接关系
- [ ] 实现 `get_page(path) → dict`
  - 按路径查询
- [ ] 验证：`operation_log` 表可写入

---

## 第四步：核心流程跑通

**文件：** `src/core/wiki_compiler.py`

- [ ] 在 `__init__` 中初始化工具和 LLM
- [ ] 实现 `ingest(source_path) → dict`
  1. `ReadTool.read_file(source_path)` ← 读 raw/
  2. `LLMAdapter.chat(prompt, system_prompt)` ← 让 LLM 编译
     - system_prompt = Wiki 编译规范（页面结构、type 分类）
     - prompt = 源文件内容
  3. `WriteTool.write_page(path, content)` ← 写入 wiki/
  4. `WikiRepository.add_page(...)` ← 记录元数据
  5. `WikiRepository.add_link(...)` ← 记录链接
- [ ] 返回 `IngestResponse(status, pages_created, pages_updated, message)`

---

## 第五步：API 能调

**文件：** `src/main.py`

- [ ] `POST /v1/ingest` → 接收 `IngestRequest` → 调用 `WikiCompiler.ingest()` → 返回 `IngestResponse`
  - `GET` 改为 `POST`，加 Pydantic 请求体验证
  - 错误处理（400/403/404/500）
- [ ] `GET /v1/query` → 接收 `question` → 返回 `QueryResponse`（可延后，Phase 2 完善）
- [ ] `GET /v1/lint` → 检查 Wiki 健康度（可延后）
- [ ] 验证：`uvicorn src.main:app --reload` 启动，API 可调通

---

## 验证标准

```bash
# 1. 启动服务
uvicorn src.main:app --reload

# 2. 调 Ingest API
curl -X POST http://localhost:8000/v1/ingest \
  -H "Content-Type: application/json" \
  -d '{"source_path": "sources/test.md"}'

# 3. 检查 wiki/ 下生成了页面
ls wiki/

# 4. 查询元数据
curl http://localhost:8000/v1/query?question=xxx

# 5. 健康检查
curl http://localhost:8000/health
```

---

## 交付物

Phase 1 完成时：

- [ ] 能调 API 把 raw/ 下的 .md 文件"编译"到 wiki/
- [ ] wiki/ 页面包含：标题、正文、双向链接、元数据
- [ ] SQLite 记录页面信息和操作日志
- [ ] 所有操作有权限校验（路径安全）
- [ ] `pytest` 测试通过
