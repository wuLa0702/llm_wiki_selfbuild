---
description: LLM Wiki 后端开发规范 — 分层/工具/LLM/DB 模式
globs: src/**/*.py
---

# 后端开发规范

## 分层架构

```
src/
├── main.py          # FastAPI 入口，路由注册
├── core/            # 核心业务逻辑（WikiCompiler, WikiMemory）
├── tools/           # Agent 工具（ReadTool, WriteTool, SearchTool）
├── llm/             # LLM 接入封装（LLMAdapter）
└── db/              # 数据访问层（WikiRepository）
```

依赖方向：`main → core → {tools, llm, db}`，禁止反向依赖。

## 核心模块规范

### WikiCompiler（核心编排器）

协调工具和 LLM 完成 Ingest/Query/Lint：

```python
class WikiCompiler:
    """单一职责：编排操作流程"""
    
    def __init__(self):
        self.reader = ReadTool()
        self.writer = WriteTool()
        self.llm = LLMAdapter()
        self.db = WikiRepository()
    
    def ingest(self, source_path: str) -> dict:
        ...
```

### Agent 工具规范

每个工具类职责单一，必须做权限校验：

| 工具 | 目录 | 权限 |
|------|------|------|
| `ReadTool` | `raw/` | 只读 |
| `WriteTool` | `wiki/` | 读写 |
| `SearchTool` | `wiki/` | 只读 |
| `LintTool` | `wiki/` | 只读 |

### LLM 适配器规范

```python
class LLMAdapter:
    """统一调用接口，LangChain 封装"""
    
    def chat(self, prompt: str, system_prompt: str = "") -> str: ...
    def chat_structured(self, prompt: str, schema: dict) -> dict: ...
```

- Provider 通过环境变量切换，不硬编码
- 所有 LLM 调用必须加 `timeout` 和 `max_retries`
- System Prompt 统一管理，不分散在各调用处

### 数据访问层规范

- 所有 SQL 写在 `schema.py` 中，DAO 层只调用不拼 SQL
- 使用 `sqlite3.Row` 作为行工厂
- 写操作必须 commit，长事务避免加锁
