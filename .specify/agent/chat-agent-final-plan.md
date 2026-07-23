# Chat Agent — P1 最终实施方案

> **状态：** 最终方案（2026-07-22，布偶猫-架构师 + 布偶猫-豆包 review 通过）
> **目标：** 在 `src/agent/` 下构建最小可行 Chat Agent，替换前端 ChatPage mock

---

## 设计决策

| 决策 | 结论 | 理由 |
|------|------|------|
| Agent 数量 | **1 个** | `create_react_agent` 的 ReAct 循环天然意图驱动，不需要 Supervisor/多 Agent |
| 工具数量（P1） | **3 个只读工具** | search_wiki, read_page, query_graph；全只读，Agent 零副作用 |
| ingest 走 Agent？ | **否** | LLM-in-LLM 问题（双层 token/超时/错误），保持直接 API |
| middleware/memory 模块 | **P1 不建** | 路径安全已有 `path_utils.py`；记忆放 P2；不重复造轮子 |
| remember_setting 工具 | **砍掉** | 设置归 SQLite settings 表，不是对话记忆 |
| 流式输出 | **SSE 必做** | ChatPage UX 要求；LangChain `astream_events()` 原生支持 |
| Agent 框架 | **`create_react_agent`（langchain）** | 不加新依赖；接口抽象预留 LangGraph 迁移 |
| API 路径 | **`POST /v1/agent/chat`** | `/v1/agent/` 命名空间留扩展空间 |

---

## P1 交付文件

```
新建：
  src/agent/__init__.py
  src/agent/tools.py          # 3 个 @tool 定义
  src/agent/agent.py          # build_agent() + chat_stream() 异步生成器
  src/api/routes/chat.py      # POST /v1/agent/chat → SSE

修改：
  src/main.py                 # 注册 chat 路由
  wiki-ui-v2/src/pages/ChatPage.tsx   # mock → 真实 SSE API
```

---

## 一、工具定义（`src/agent/tools.py`）

### 1. `search_wiki(query: str) -> str`

- **输入：** 搜索关键词
- **输出：** 匹配页面列表（标题 + 路径 + 摘要），文本格式
- **底层：** `src.core.search.SearchTool.search()`
- **说明：** Agent 回答问题的第一步——找到相关页面

### 2. `read_page(path: str) -> str`

- **输入：** 页面相对路径（如 `entities/异步编程.md`）
- **输出：** 页面正文（去掉 YAML frontmatter，截断到 4000 字符）
- **底层：** 直接读 `wiki/` 目录文件（复用 WriteTool 的 base_dir）
- **路径安全：** 校验前缀在 `wiki/` 下，防路径穿越
- **说明：** search 结果不够时，读全文获取详细内容

### 3. `query_graph(question: str) -> str`

- **输入：** 自然语言问题
- **输出：** 相关实体、社区、关联路径的文本描述
- **底层：** `src.core.graph.WikiGraph`（社区发现 + 邻居查询）
- **说明：** P1.5 优先级；search + read 跑通后再加，用于发现隐含关联

### 工具函数签名（LangChain @tool）

```python
from langchain_core.tools import tool

@tool
def search_wiki(query: str) -> str:
    """搜索 Wiki 知识库，返回匹配页面列表（标题、路径、摘要）。
    当需要回答用户问题时，优先使用此工具找到相关页面。"""
    ...

@tool
def read_page(path: str) -> str:
    """读取指定 Wiki 页面的完整正文内容（已去掉 frontmatter）。
    路径格式如 'entities/异步编程.md'。在 search_wiki 找到相关页面后使用。"""
    ...

@tool
def query_graph(question: str) -> str:
    """查询知识图谱，返回与问题相关的实体关联和社区信息。
    用于发现搜索关键词不直接匹配的隐含知识关联。"""
    ...
```

---

## 二、Agent 构建（`src/agent/agent.py`）

### 核心约束

- 导出接口固定：`async def chat_stream(messages: list[dict]) -> AsyncIterator[dict]`
- 从 ReAct 切到 LangGraph 时，**路由层和前端一行不改**
- 复用项目的 `LLMAdapter`（不直接 new ChatOpenAI，保持 provider 可切换）

### System Prompt

```
你是 LLM Wiki 的知识助手。你可以搜索、阅读、分析知识库中的内容来回答用户问题。

规则：
1. 回答必须基于 Wiki 页面内容，不要编造信息
2. 不确定时先调用 search_wiki 找到相关页面，再用 read_page 获取详情
3. 引用页面时使用 [[页面路径]] 格式，用户可点击跳转
4. 如果知识库中没有相关内容，明确告知用户，不要编造
5. 使用中文回答（除非用户用其他语言提问）
6. 回答要简洁准确，适当使用 Markdown 格式
```

### chat_stream 产出事件格式

统一 dict 格式，SSE 按 type 分流：

```python
{"type": "token", "content": "异步"}                    # 逐 token 流式
{"type": "tool_start", "tool": "search_wiki", "input": {"query": "..."}}
{"type": "tool_end", "tool": "search_wiki", "output": "..."}
{"type": "done", "sources": ["entities/异步编程.md"]}   # 结束，附引用来源
{"type": "error", "message": "..."}                     # 异常
```

---

## 三、API 路由（`src/api/routes/chat.py`）

### 请求

```
POST /v1/agent/chat
Content-Type: application/json

{
  "messages": [
    {"role": "user", "content": "什么是异步编程？"}
  ]
}
```

- P1 无记忆，前端每次发完整对话历史
- P2 加 `conversation_id` 字段，后端做记忆持久化

### 响应（SSE）

```
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive

event: message
data: {"type": "token", "content": "异步"}

event: message
data: {"type": "tool_start", "tool": "search_wiki", "input": {"query": "异步编程"}}

event: message
data: {"type": "done", "sources": ["entities/异步编程.md"]}
```

- 使用 `StreamingResponse` (FastAPI) + `async generator`
- 异常时发送 `{"type": "error", ...}` 事件后关闭流

---

## 四、前端改造（`wiki-ui-v2/src/pages/ChatPage.tsx`）

1. 删除现有 `MOCK_RESPONSES` 模拟数据
2. 用 `EventSource` / `fetch + ReadableStream` 连接 SSE
3. 按事件 type 分流渲染：
   - `token` → 追加到 assistant 消息气泡（打字机效果）
   - `tool_start/tool_end` → 显示"正在搜索..."状态提示
   - `done` → 渲染 [[wikilinks]] 为可点击链接
   - `error` → 显示错误提示
4. 解析回答中的 `[[路径]]` 渲染为内部链接（点击跳转 `/wiki?path=...`）

---

## 五、实施顺序（TDD）

1. **写工具单元测试**（mock SearchTool / 文件读取）
2. **实现 tools.py**（3 个 @tool）
3. **写 agent 集成测试**（mock LLM，验证工具调用链路）
4. **实现 agent.py**（build_agent + chat_stream）
5. **写路由测试**（TestClient + SSE 流解析）
6. **实现 chat.py 路由**
7. **注册到 main.py**
8. **改前端 ChatPage**
9. **端到端验证**：启动服务 → 问测试问题 → 确认流式输出 + 工具调用正常

---

## P2/P3 路线

```
P2：对话记忆
  ├── 加 conversation_id，后端持久化对话历史
  ├── 方案：langgraph checkpointer（SQLite）或 ConversationSummaryBufferMemory
  └── 前端 ChatPage 加对话列表侧边栏

P3：运维写工具（非 ingest）
  ├── trigger_lint() → 触发知识库 lint 检查
  ├── rebuild_index() → 重建 BM25/向量搜索索引
  └── graph_insights() → 图谱洞察报告

P4+：对话化摄入（远）
  └── 用户粘贴文本 → Agent 分析 → 确认 → 调用 ingest
      （带确认环节，非自动调用）
```

### 设计铁律（不可违反）

1. **ingest 永不作为 Agent 自动调用工具**（LLM-in-LLM 问题）
2. **P1 全只读工具，Agent 无法产生副作用**
3. **agent.py 的 `chat_stream()` 接口固定**，换 LangGraph 时对外透明
4. **工具层单向依赖**：Agent → tools.py → 现有 src/tools/ + src/core/，反向零依赖
5. **复用不重写**：路径安全用 `path_utils.py`，LLM 用 `LLMAdapter`，搜索用 `SearchTool`

---

## 依赖确认

现有 requirements.txt 已有：
- `langchain-core>=0.3.0`
- `langchain-openai>=0.2.0`

`create_react_agent` 在 `langchain` 包中，需确认是否已安装：
```python
from langchain.agents import create_react_agent
```
如果 `langchain` 主包未安装，P1 第一步 `pip install langchain`。
