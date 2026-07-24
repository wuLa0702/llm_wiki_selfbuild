# Agent 手写训练 — 问题记录与解答

> 2026-07-23 初始记录
> 对应文件：`src/agent/agent.py`（手写版 `chat_stream`）

---

## Agent 学习路线图

> 核心理念：**先依 LangChain 写完大部分，再通过 LangGraph 局部优化。**
> 不贪多求快，每层学扎实再进下一层。

```
前置基础
      ↓
LangChain（组件积木）
      ↓
LangGraph ⭐【重中之重】
      ├─ 状态、循环、断点、人在回路
      └─ 原生手写：单智能体 → 原生多智能体
      ↓
DeepAgents（预制 Harness 套件，基于 LangGraph）
      ↓
多智能体高阶模式 + 对接前端 Agent Chat UI
      ↓
Agent Harness 架构思想（脱离框架，自研生产级底座）
```

### 各层说明

| 层级 | 目标 | 手写重点 | 文档 |
|:-----|:-----|:---------|:-----|
| **前置基础** | Python 异步、类型注解、生成器 | `yield`、`async for`、`getattr`、切片 | Python 官方教程 |
| **LangChain** | 掌握积木：Message、Tool、Prompt、Model | `@tool` 协议、消息转换、`create_agent` 参数 | https://docs.langchain.org.cn/oss/python/langchain/agents |
| **LangGraph** ⭐ | 状态图、循环、断点、人在回路 | `StateGraph` 手搭节点/边、条件分支、检查点 | https://langchain-ai.github.io/langgraph/ |
| **DeepAgents** | 使用预制 Harness 搭建完整 Agent | 中间件、动态模型/工具、结构化输出 | https://docs.langchain.org.cn/oss/python/langchain/agents |
| **多智能体+前端** | 多 Agent 编排、Agent Chat UI 对接 | 路由、技能、子 Agent 流式 | https://docs.langchain.org.cn/oss/python/langchain/multi-agent/ |
| **Harness 架构** | 脱离框架，自研生产级底座 | 抽象框架共性，设计自有架构 | — |

### 学习纪律

- 每层第一个 Demo **强制手写**
- 同一个模式成功手写 1~2 次后，放开 Vibe Coding 提速
- 核心逻辑手写，样板代码 AI 生成
- 遇到问题先写 `.learnings/` 记录，每日复习

---

## @tool 手写训练记录（2026-07-23）

> 对应文件：`src/agent/tools.py` — 手写 `search_wiki` 函数

### 发现的 Bug

| # | 问题 | 根因 | 修法 |
|:-:|:-----|:-----|:-----|
| 1 | `search_tool.search()` 返回值丢了 | 没赋值，结果直接丢弃 | `results = st.search(...)` |
| 2 | `if not result:` 报错 | `result` 是从 `sqlalchemy` 错误导入的，不是搜索结果 | 删错误导入，变量名改 `results` |
| 3 | `title` 未定义就使用 | 第 `r.get("title") or Path(path).stem` 没有赋值 | `title = r.get(...) or ...` |
| 4 | 两个无关导入 | 可能 AI 补全带入 | 删除 `onnxruntime` 和 `sqlalchemy` 导入 |

### @tool 协议理解

**Q: `@tool(name_or_callable="search_wiki")` 和 `@tool` 有什么区别？**
A: `name_or_callable` 是 `@tool` 内部第一个参数。写 `@tool` 就行，函数名自动成为 tool name。只有在想给 tool 起一个和函数名不同的名字时才需要用 `name="xxx"`。

**Q: 为什么不用 ToolNode 包裹？**
A: `@tool` 和 `ToolNode` 是两层的概念：
```
@tool（LangChain 层）→ 把函数变成 Tool 对象，供 LLM 知道"有这个工具"
ToolNode（LangGraph 层）→ 在图中执行工具的节点，自动从 tool_calls 取参数调用
```
当前在 LangChain 层学习，只用 `@tool`。等学到 LangGraph 才需要用 `ToolNode`。

**Q: tool 需要访问请求上下文吗？**
A: 当前不需要（纯只读），以后如果要做用户权限过滤，可以用 `ToolRuntime` 参数，但那是 P2 的事。

### 代码设计思考

| 写法 | 含义 |
|:-----|:------|
| `title = r.get("title") or Path(path).stem` | 优先用标题，没有则用文件名当标题（兜底） |
| `snippet[:200].replace("\n", " ")` | 截断 200 字符 + 换行变空格 → 摘要在一行内 |
| `"\n".join(lines)` | 列表用换行符拼成字符串，每行一条结果 |
| `"这里应该用对象"` → P2 再抽成 Formatter 类 | 当前先跑通，不提前抽象 |

### day1 检查

复习问题：
- [ ] `@tool` 装饰器把函数变成了什么对象？
- [ ] 函数的 docstring 去了 tool 的哪个属性？
- [ ] `ToolNode` 和 `@tool` 的关系是什么？
- [ ] `r.get("title") or Path(path).stem` 的 `or` 是什么逻辑？

---

## ReAct 手写循环记录（2026-07-23）

> 对应文件：`sandbox/agent/phase1_basic_agent/03_react_manual.py`
> 目标：在不使用 `create_react_agent` 的情况下，手动实现 Agent 的思考→行动→观察循环

### ReAct 循环的本质

```
┌──────────┐   有 tool_calls     ┌──────────┐
│ 调 LLM   │ ──────────────────→ │ 执行工具  │
│          │                     │          │
│ 返回消息 ├←──────────────────── │ 返回结果  │
└──────────┘  把结果追加到消息列表  └──────────┘
     │
     │ 没有 tool_calls
     ↓
┌──────────┐
│ 最终回答  │
└──────────┘
```

**一句话：** 调 LLM → 看要不要调工具 → 调工具 → 结果塞回消息列表 → 再调 LLM ... 直到 LLM 直接回答。

### 关键数据流

```
messages = [
    HumanMessage("3+5等于多少？"),   ← 用户提问
    AIMessage(                         ← LLM 决定调工具
        content="",
        tool_calls=[{"name":"add", "args":{"a":3,"b":5}, "id":"call_xxx"}]
    ),
    ToolMessage(                       ← 工具执行结果
        content="8",
        tool_call_id="call_xxx"        ← 这个 ID 配对上面的 tool_call
    ),
    AIMessage(content="3+5=8"),       ← LLM 看到结果后给出最终回答
]
```

关键点：**消息列表就是 Agent 的记忆**。每次工具结果追加进去，LLM 下一次调用就能看到。

### 手写循环 vs create_react_agent

| | 手写循环 | create_react_agent |
|:--|:---------|:-------------------|
| 做了什么 | 手动调 LLM → 检查 tool_calls → 执行工具 → 拼接消息 | 自动做同样的事 |
| 你能看到的 | 每一步的 messages 追加过程 | 内部是一个黑盒 |
| 额外功能 | 无 | 流式输出、状态管理、错误重试 |
| 适合阶段 | P1 理解原理 | P2 生产使用 |

### 你 hand-write 了什么

在 `03_react_manual.py` 中：
1. ✅ `bind_tools` — 让 LLM 知道工具有哪些
2. ✅ `react_loop()` — 手动循环：invoke → 检查 tool_calls → 执行工具 → 拼接 ToolMessage → 继续
3. ✅ `ToolMessage(tool_call_id=...)` — 理解 tool_call 和 tool_result 如何配对
4. ✅ 多步推理（如 `(3+5)×2` 需要 add → multiply 两步）

### 下一步你可以尝试

1. 把 `TOOLS` 换成 Wiki 工具（`search_wiki`、`read_page`）
2. 加流式输出（`llm.stream` 替代 `llm.invoke`）
3. 加多轮对话（把 messages 存到外面）
4. 然后进 LangGraph，用 `StateGraph` 来管理这个循环

### day1 检查
- [ ] 能用一句话描述 ReAct 循环吗？
- [ ] `ToolMessage` 的 `tool_call_id` 是干什么的？
- [ ] 为什么 `messages` 列表就是 Agent 的记忆？
- [ ] 手写循环和 `create_react_agent` 的关系是什么？

---

## P1 Agent 架构问题记录与追踪（2026-07-23）

> 阅读官网代理模块时的思考，逐条记录方便复盘。

### 问题清单

| # | 问题 | 结论 | 归属 |
|:-:|:-----|:-----|:----:|
| 1 | 需要动态模型吗？模型切换在哪？ | 不需要动态。切换在 `config.py` + 前端设置页，P1 固定 DeepSeek | P2 加 API model 参数 |
| 2 | 动态工具用得上吗？ | 用不上，3 个静态工具对所有用户一致 | 未来多用户权限时考虑 |
| 3 | 工具错误处理做了吗？ | 做了基础版（try/except return str），没做框架级（ToolException） | P2 升级到 ToolException |
| 4 | ReAct 中 AI 自己选工具？ | 是。靠 `@tool` 的 docstring(description)，LLM 自己判断用哪个 | 已在用，需优化描述精度 |
| 5 | 系统提示词用不用？ | 用。`SYSTEM_PROMPT` 已传入 `create_agent(system_prompt=...)` | 已实现 |
| 6 | Agent 名称需要吗？ | 单 agent 不重要，`name="wiki_agent"` 已设 | 多 agent 时有用 |
| 7 | 并行多对话支持吗？ | 不支持。全局单例 + 无 thread_id | P2 加 MemorySaver + thread_id |

### P1 完成度检查

| # | P1 任务 | 状态 | 说明 |
|:-:|:--------|:----:|:-----|
| 1 | `chat_stream` 手写（消息转换 + SSE 事件） | ✅ 完成 | 已手写并修复，生产可用 |
| 2 | `@tool` 手写（search_wiki） | ✅ 完成 | 已手写，3 个 Bug 已修，生产可用 |
| 3 | ReAct 循环理解（手写模拟） | 🟡 有范例 | `03_react_manual.py` 已写，用户可自主运行学习 |
| 4 | `build_agent()` 跑通（create_agent） | ✅ 完成 | 生产端到端可用 |
| 5 | `POST /v1/agent/chat` 端点 | ✅ 完成 | SSE 流式正常 |
| 6 | 多轮对话记忆 | ❌ P2 | 需要 MemorySaver + thread_id |
| 7 | 会话隔离 | ❌ P2 | 同上 |

**结论：P1 核心功能已跑通，可以进入 P2（LangGraph）。**

---

## 第一层：Python 基础语法

### Q1: `yield` 是什么？

**A:** `yield` 是 Python **生成器（Generator）** 的关键字。

普通函数用 `return` 返回一次就结束；生成器函数用 `yield`，每次 `yield` 返回一个值，函数状态"暂停"，下次调用时**接着往下走**。

```python
def gen_numbers():
    yield 1
    yield 2
    yield 3

for n in gen_numbers():  # 输出 1, 2, 3
    print(n)
```

在 `chat_stream` 里，每次 `yield {"type": "token", "content": "..."}` 就是把一个事件"吐"给调用者（SSE 流），调用者用 `async for` 逐个消费。

> **联想记忆**：`return` = 快递一次到终点；`yield` = 自动售货机，按一下掉一个。

---

### Q2: `list[-MAX_MESSAGE_TURNS:]` 切片语法看不懂

**A:** 这是 Python 列表切片（slice）—— `list[start:stop:step]`。

```python
arr = [0, 1, 2, 3, 4, 5]
arr[-3:]   # → [3, 4, 5]  取最后 3 个
arr[:3]    # → [0, 1, 2]  取前 3 个
arr[1:4]   # → [1, 2, 3]  索引 1~3（左闭右开）
```

- 负数索引：`-1` = 最后一个，`-2` = 倒数第二个……
- `list[-N:]` = 取列表**最后 N 个元素**
- `non_system[-MAX_MESSAGE_TURNS:]` = 只保留最近的 20 轮非 system 消息

---

### Q3: `getattr(chunk, "content", "")` 是什么？

**A:** `getattr(obj, name, default)` 是 Python **内置函数**，安全地获取对象的属性。

```python
# 等价于 chunk.content，但更安全
content = getattr(chunk, "content", "")
# 如果 chunk 没有 content 属性，返回 "" 而不是抛 AttributeError
```

为什么用它？因为 `astream_events` 返回的事件中 `chunk` 可能是多种类型（AIMessageChunk 或其他），用 `getattr` 避免了写 try/except。

---

### Q4: `if content:` 直接判空了么？

**A:** 是的。Python 的**真值测试**：空字符串 `""`、`None`、`0`、空列表 `[]` 都是 `False`。

```python
content = ""     # bool(content) → False
content = "你好" # bool(content) → True
```

所以 `if content:` 等价于 `if content != "" and content is not None:`，更简洁。

---

### Q5: `list[dict]` 是什么？外层是 list 链表还是数组？内层 dict 是什么结构？

**A:** 
- **外层** `list`：Python 的列表（动态数组），不是链表。支持索引 `[0]`、`append()`、`len()`。
- **内层** `dict`：字典（键值对），类似 JSON 对象。

入参示例：
```python
messages = [
    {"role": "user", "content": "什么是 LangGraph？"},
    {"role": "assistant", "content": "LangGraph 是..."},
    {"role": "user", "content": "继续讲"},
]
```

`list[dict]` 是类型注解（Python 3.9+），表示"一个列表，里面每个元素是字典"。

---

### Q6: `lc_messages` 的 `lc` 是什么缩写？

**A:** **LangChain** 的缩写。这是 LangChain 社区约定俗成的命名前缀：
- `lc_messages` = LangChain 格式的消息对象列表
- 普通 `messages`（dict 列表）→ 转换后 → `lc_messages`（HumanMessage 等对象）

> 好的命名应该让人一眼看出含义，`lc_messages` 对新手不友好。可以考虑改成 `langchain_messages` 更清晰。

---

### Q7: 循环里 `import re` 会重复导入吗？

**A:** 不会报错，但**风格上不对**。

Python 的 `import` 有缓存机制：第二次 `import re` 只是从 `sys.modules` 取已加载的模块，不会重新执行。但：
1. **性能浪费**：每次循环都查一次缓存
2. **可读性差**：`import` 应该统一在文件顶部
3. **PEP 8 规范**：所有 import 必须放文件开头

✅ 正确做法：文件顶部写 `import re`

---

### Q8: `content=content` 为什么是红色？是强制指定参数名吗？

**A:** `HumanMessage(content=content)` 是**关键字参数**调用。

- 左边 `content=` 是参数名（keyword argument）
- 右边 `content` 是前面定义的变量值

红色高亮可能是 IDE（VS Code/PyCharm）的语法着色——关键字参数用特定颜色标记，帮助区分参数名和变量值。

不是"强制指定"——你也可以按位置传参：
```python
HumanMessage(content)  # 位置参数，但从可读性看不如 keyword
```

LangChain 的 `HumanMessage(content="...")` 在构造函数里 `content` 是第一个位置参数，但**明确写参数名是更好的风格**。

---

### Q9: `sources: list[str] = []` 这行是干嘛的？

**A:** 这是一个**类型注解**的变量声明：
- `sources`：变量名
- `list[str]`：这是一个字符串列表（Python 3.9+ 语法，等价于 `List[str]`）
- `= []`：初始化为空列表

好的命名+注释应该能自解释。这里缺注释，改进建议：
```python
# 收集工具调用中引用的 wiki 页面路径，用于最终返回来源列表
sources: list[str] = []
```

---

## 第二层：LangChain 框架概念

### Q10: `HumanMessage` 是什么？官方文档在哪里？中文镜像呢？

**A:** `HumanMessage` 是 LangChain 中表示**用户消息**的类。

LangChain 的消息体系：
| 类 | 含义 | 对应角色 |
|---|---|---|
| `SystemMessage` | 系统提示词，设定 AI 人格 | system |
| `HumanMessage` | 用户输入 | user |
| `AIMessage` | AI 回复（含 tool calls） | assistant |
| `ToolMessage` | 工具调用结果 | tool |

**官方文档：**
- Python 消息体系：https://docs.langchain.org.cn/oss/python/langchain/messages
- 英文原版：https://python.langchain.com/docs/concepts/#messages

（已配好 `docs-langchain` MCP，可直接查询）

---

### Q11: `astream_events` 有这个事件吗？点不进去

**A:** `astream_events` 是 LangChain 的**异步流式事件 API**（v0.1+ 引入）。

类型提示里看不到是因为：
1. 可能 `LangChain` 版本安装的不是最新
2. VS Code 的 Pylance 类型推断需要运行 `pip install types-langchain` 或装 `langchain-core` 的类型 stub
3. 这个方法是动态注册的，部分 IDE 无法跳转到源码

**官方文档：**
- Python 流式/Runtime（含 astream_events）：https://docs.langchain.org.cn/oss/python/langchain/runtime
- 英文 Creating Agents：https://docs.langchain.com/oss/python/langchain/agents

常用事件类型：
| 事件名 | 触发时机 |
|---|---|
| `on_chat_model_stream` | LLM 输出 token |
| `on_tool_start` | 工具调用开始 |
| `on_tool_end` | 工具调用结束 |
| `on_chain_start/end` | Chain 开始/结束 |

---

### Q12: 哪里定义的不同 type 用不同参数？每个方法都要去官方查参数？

**A:** 是的，`astream_events` 的**事件结构**确实需要查文档。

LangChain 定义了一套标准事件 schema，每个 `kind` 对应的 `data` 结构不同：
- `on_chat_model_stream` → `data.chunk` = AIMessageChunk
- `on_tool_start` → `data.input` = dict
- `on_tool_end` → `data.output` = str

**经验法则**：框架的流式 API 都需要查文档；业务代码才自己设计。

这也是为什么手写训练有价值——写一次就知道 schema 长什么样了，后面不用反复查。

---

### Q13: 为什么 `type` 叫 `"token"`？

**A:** 因为 `on_chat_model_stream` 事件的每次回调，LLM 返回的是一个**文本片段**（token）。

LLM 的流式输出原理：模型不是一次性生成全部文字，而是一个 token 一个 token 地吐。流式 API 把每个 token 实时推给前端，前端逐字显示。

所以 `yield {"type": "token", "content": "..."}` 中的 "token" 就是"一个文本片段"的意思，SSE 前端收到后追加到对话气泡中。

> 注：这里的 "token" 不是 LLM 的 BPE token（词元），而是"一段文本碎片"。每个 yield 可能是 1~N 个字符。

---

## 第三层：架构设计思考

### Q14: `agent: object` — 为啥是 object？这里放任何类型都可以？

**A:** 是的，`object` 是 Python 所有类的基类，标注 `object` 等于"不限制类型"，失去了类型检查的意义。

✅ 已改为具体类型：
```python
from langgraph.graph.state import CompiledStateGraph

def chat_stream(
    agent: CompiledStateGraph,  # create_agent 返回的准确类型
    ...
```

`create_agent()` 返回 `CompiledStateGraph`（继承自 LangGraph 的 `StateGraph.compile()` 返回值）。标注清楚后：
1. IDE 可以自动补全方法和属性（如 `.astream_events()`）
2. 类型检查可以提前拦截错误调用

---

### Q15: 没有一个结构体么？这里硬编码？

**A:** 好问题！Python 有两种方式：

1. **类型注解**（当前方式，轻量）：
```python
messages: list[dict]
```
优点：简单，不需要额外定义；缺点：IDE 不知道 dict 里面具体有什么字段。

2. **Pydantic 模型**（结构化）：
```python
from pydantic import BaseModel

class Message(BaseModel):
    role: str = "user"
    content: str = ""
```
优点：类型安全、自动校验、IDE 友好；缺点：多一层定义。

**折中方案**：用 `TypedDict`（Python 3.8+），既有结构安全又轻量：
```python
from typing import TypedDict

class Message(TypedDict):
    role: str
    content: str
```

**结论**：当前硬编码没问题，P1 阶段先跑通。P2 用 TypedDict 替换。

---

### Q16: 消息裁剪逻辑放在后端？不应该前端做折叠，后端做压缩？

**A:** 你的思路**完全正确**！当前方案是 P1 的临时策略：

```
P1（当前）: 后端直接丢弃旧消息 → 简单粗暴但能跑
P2（未来）: ConversationSummaryMemory / 滑动窗口压缩 → 保留语义
```

**为什么 P1 这么写？**
1. 为了快速让 Agent 不炸 token 限制
2. `MAX_MESSAGE_TURNS = 20` 是一个保守值

**理想方案（你的思路）**：
- 前端：消息列表展示全部历史（可以折叠）
- 后端：超过窗口后做**语义压缩**（调用 LLM 摘要历史对话），而不是简单丢弃

LangChain 提供了现成的解决方案：
- `ConversationSummaryMemory` — 自动摘要历史
- `ConversationTokenBufferMemory` — 按 token 数裁剪

**你的思考方向是对的，这代表你已经进入工程化思维阶段！**

---

## Q17: `async for` + `AsyncIterator`？`async` 关键字是什么？

**A:** Python 的异步编程语法：

| 同步 | 异步 |
|---|---|
| `def func()` | `async def func()` |
| `for x in iter:` | `async for x in aiter:` |
| `return value` | `yield value` / `return value` |
| `result = func()` | `result = await func()` |

`AsyncIterator[dict]` 表示：这是一个**异步迭代器**，每次迭代产生一个 `dict`。

前端用 SSE 接收这些事件：
```python
# 后端 yield → SSE 事件流
yield {"type": "token", "content": "你好"}

# 前端收到 → 追加到对话气泡
```

---

## 问题分类收尾（2026-07-23 更新）

### ✅ P1 — 本轮已修复（代码已改）
| 问题 | 改动 |
|:-----|:-----|
| 🐛 P0: 重复函数定义 | 删除了 AI 版 `chat_stream`（第 64-161 行），只保留手写版 |
| 🐛 P0: 错误导入 | 删除了 `Crypto.SelfTest` 和 `routes.system` 两行无效导入 |
| 🐛 P1: `agent: object` | 改为 `CompiledStateGraph`（`from langgraph.graph.state`） |
| 🐛 P1: 缺少 `on_tool_end` yield | 补充了 `yield {"type": "tool_end", ...}` 事件 |
| 🐛 P1: `import re` 在循环内 | 移到文件顶部，删除循环内 `import re` |
| 🐛 P1: `build_agent() -> object` | 改为 `build_agent() -> CompiledStateGraph` |

### 📅 P2 — 后续优化
| 问题 | 计划方案 |
|:-----|:---------|
| 消息结构体 | P2 用 `TypedDict` 替代硬编码 dict |
| 消息压缩 | 用 `ConversationSummaryMemory` 替代简单截断 |
| 前端折叠 | 前端展示全部历史可折叠，后端做语义压缩 |
| `lc_` 命名 | 改名 `langchain_messages` 更清晰 |
| `sources` 缺注释 | 加注释说明用途 |

### 📖 学习笔记保留（不修，作为记录）
- Python 语法类所有 Q&A（yield、切片、getattr、真值测试等）
- LangChain 概念类所有 Q&A（HumanMessage、astream_events 事件 schema 等）
- 架构思考类所有 Q&A（类型标注、结构体、压缩策略等）
- 代码中的 `# ask` 注释保留，作为手写训练的过程记录

---

## 官方文档速查表

> 文档镜像：`https://docs.langchain.org.cn/oss/python/langchain/<topic>`
> 全站索引（找所有页面）：https://docs.langchain.org.cn/llms.txt

| 内容 | 中文镜像（已确认有效） | 英文原版 |
|:-----|:-----------------------|:---------|
| 📦 **消息体系 Messages** | https://docs.langchain.org.cn/oss/python/langchain/messages | https://docs.langchain.com/oss/python/langchain/messages |
| 🤖 **Agent 代理（create_agent）** | https://docs.langchain.org.cn/oss/python/langchain/agents | https://docs.langchain.com/oss/python/langchain/agents |
| ⚡ **流式 Runtime** | https://docs.langchain.org.cn/oss/python/langchain/runtime | https://docs.langchain.com/oss/python/langchain/runtime |
| 🧠 **Models（含 Streaming）** | https://docs.langchain.org.cn/oss/python/langchain/models | https://docs.langchain.com/oss/python/langchain/models |
| 🛠️ **Tools 工具** | https://docs.langchain.org.cn/oss/python/langchain/tools | https://docs.langchain.com/oss/python/langchain/tools |
| 🔗 **LangGraph 官方** | — | https://langchain-ai.github.io/langgraph/ |
| 🏠 **文档首页** | https://docs.langchain.org.cn/oss/python/langchain/overview | https://docs.langchain.com/oss/python/langchain/overview |

> 💡 已配置 `docs-langchain` MCP，可在对话里直接问：`LangChain 的 xxx 是什么？`
> 💡 站点索引：`https://docs.langchain.org.cn/llms.txt` — 包含该站点所有页面路径

---

## 复习要点（每天早上看）

### 一句话记住每个概念
| 概念 | 一句话 |
|---|---|
| `yield` | 自动售货机，按一下掉一个 |
| 切片 `[-N:]` | 取列表最后 N 个 |
| `getattr(obj, "attr", default)` | 安全取属性，没有就返回默认值 |
| `if content:` | 判空，等价于 `!= "" and is not None` |
| `list[dict]` | 列表里每个元素是字典 |
| `lc_` 前缀 | LangChain 的缩写，表示"转换后的 LangChain 对象" |
| `HumanMessage` | LangChain 的用户消息类 |
| `astream_events` | LangChain 的流式事件 API |
| `async for` | Python 异步迭代 |
| `CompiledStateGraph` | `create_agent()` 的返回类型，LangGraph 编译后的图 |
| `import` 放顶部 | PEP 8 规范，不要写在循环里 |

### 本轮改动 Checklist ✅
- [x] 删除重复的 `chat_stream` 定义
- [x] 删除错误导入（`Crypto.SelfTest` / `routes.system`）
- [x] 把 `agent: object` 改成 `agent: CompiledStateGraph`
- [x] `import re` 提到文件顶部
- [x] 补充 `on_tool_end` 的 yield 事件
- [x] `build_agent() -> object` → `-> CompiledStateGraph`

---

## 第二轮：LangGraph StateGraph 手写 — Bug 修复经验（2026-07-23）

> 对应文件：`src/agent/agent.py` — 从 LangChain `create_agent` 切换为手写 `StateGraph`
> 触发源：[豆包的分析] 指出手写代码中的 3 个运行时 Bug + 2 个代码质量问题

### 3 大 Bug 模式（手写 LangGraph 必知）

#### Bug 1: AIMessage 对象当 dict 用

```python
# ❌ 错误 — AIMessage 不支持 dict 下标
state_messages["type"] == "tool_calls"

# ✅ 正确 — 用 hasattr + 属性访问
hasattr(last_msg, "tool_calls") and last_msg.tool_calls
```

**根因**：`state["messages"][-1]` 返回 `AIMessage` 对象，不是 dict。Python 新手常混淆"长得像 dict 的对象"和"真的是 dict"。LangChain 的 Message 体系全是对象，访问字段用 `.` 而不是 `["key"]`。

**预防**：给 `AgentState` 加上精确类型 `list[BaseMessage]` → IDE 就知道 `[-1]` 是 `BaseMessage`，自动提示 `.tool_calls` / `.type` 等属性。

#### Bug 2: 条件边返回值不匹配节点名

```python
# ❌ 错误
def should_continue(...) -> Literal["tools", "__end__"]:
    return "tool_calls"  # ← 节点注册为 "tools"，不是 "tool_calls"

# ✅ 正确
def should_continue(...) -> Literal["tools", "__end__"]:
    return "tools"
```

**根因**：`add_node("tools", tool_node)` 注册的节点名为 `"tools"`；条件边返回值必须**精确匹配**节点注册名。`return "tool_calls"` 相当于让 LangGraph 路由到一个不存在的节点，抛 `ValueError`。

**LangGraph 路由规则**：
```
条件边返回值 → LangGraph 用此值查找该名称的节点
节点名 → add_node("name", fn) 中的 "name"
两者必须完全一致（字符串精确匹配）
```

**内置节点名**：
| 节点 | 说明 |
|------|------|
| `"__start__"` | 图入口，自动生成 |
| `"__end__"` | 图终止，内置常量 `END` |
| 自定义 | `add_node("agent", ...)` → 路由到 `"agent"` |

#### Bug 3: AgentState 字段冗余 + 类型不精确

```python
# ❌ 旧代码
class AgentState(TypedDict):
    messages: list           # 太宽泛——须是 BaseMessage 子类
    next: str               # 未使用——图路由由条件边控制

# ✅ 新代码
class AgentState(TypedDict):
    messages: list[BaseMessage]  # 精确约束，IDE 可推导元素类型
```

**原则**：
- **只声明运行时必需的字段** — `next` 从未被任何节点读写，属于 OOP 过度设计
- **类型尽可能精确** — `list` → `list[BaseMessage]` 让 IDE 能推导元素类型
- **LangGraph 的状态缩减**：编译阶段自动丢弃未使用的状态键，但定义时仍要精简

### 架构分层经验

最终 `agent.py` 的清晰分层（从上线到下读）：

```
┌─────────────────────────────────────────┐
│  模块 docstring → 导出接口声明           │
├─────────────────────────────────────────┤
│  imports（stdlib → third-party → 内部）  │
├─────────────────────────────────────────┤
│  SYSTEM_PROMPT                          │  纯配置
│  P1_TOOLS = [search_wiki, read_page]    │
│  MAX_MESSAGE_TURNS = 20                 │
├─────────────────────────────────────────┤
│  class AgentState(TypedDict)            │  类型定义
├─────────────────────────────────────────┤
│  llm = ChatOpenAI(...)                  │  资源初始化
│  llm_with_tools = llm.bind_tools(...)   │
├─────────────────────────────────────────┤
│  def call_model(state) → dict           │  图节点
│  tool_node = ToolNode(...)              │
│  def should_continue(state) → Literal   │
├─────────────────────────────────────────┤
│  builder = StateGraph(AgentState)       │  图构建
│  builder.add_node / add_edge / compile  │
├─────────────────────────────────────────┤
│  def build_agent() → CompiledStateGraph │  对外接口
│  async def chat_stream(...)             │
└─────────────────────────────────────────┘
```

**关键原则**：
- 配置在上，逻辑在下 — 读文件时从上到下越来越具体
- 接口在底 — `build_agent()` / `chat_stream()` 是模块的导出面
- `build_agent()` 是**纯工厂** — 只返回编译好的图，不做无关的 `LLMAdapter` 初始化

### 豆包回答 vs 之前回答的差异分析

| 维度 | 之前回答（Session #1） | 豆包回答 | 经验 |
|:-----|:----------------------|:---------|:-----|
| Bug 定位 | 提了"代码有 Bug"，但没展开 | 逐行指出 `should_continue` 的 2 个致命 Bug | **Bug 必须给精确的"错误行号 + 根因 + 修复代码"——不说"有 Bug"，说"第 N 行：...错误，因为..."** |
| 结构 | 大段文字混在一起 | 按 `ask` 编号逐条拆解，每条 `代码块 + 原因 + 修复` | **结构化输出比长段落更易消化——编号 + 标题 + 对比代码块** |
| 缺陷覆盖 | 只提了主要问题 | 额外发现了 `build_agent` 无用代码、`next` 冗余、TODOs 清理 | **做完整审计，不只看明显问题** |
| 输出格式 | 5 段式框架没坚持 | 逐 ask 问答 + 额外诊断 + 架构总结 | **固定格式虽然好，但逐条追 ask 更能满足"每个小问都被回答"的安心感** |

### LangGraph 手写 Checklist（更新版）

**Day 1 基础检查（ReAct 循环理解）**：
- [ ] 能用一句话描述 ReAct 循环吗？
- [ ] `ToolMessage` 的 `tool_call_id` 是干什么的？
- [ ] 为什么 `messages` 列表就是 Agent 的记忆？

**LangGraph 图结构检查**：
- [ ] `AgentState` 的字段都是运行时必要的吗？
- [ ] `messages` 的类型是 `list[BaseMessage]` 还是裸 `list`？
- [ ] 条件边的返回值精确匹配了节点名吗？
- [ ] `hasattr(msg, "tool_calls")` 替代了 `msg["type"]` 吗？
- [ ] `build_agent()` 只做工厂返回，没有多余逻辑吗？
- [ ] import 分三组（stdlib / third-party / 内部）且无重复吗？

### 当前 git 状态（2026-07-23 第二轮修复后）

| 文件 | 状态 | 说明 |
|:-----|:----:|:-----|
| `src/agent/agent.py` | ✅ 修复 | LangGraph 手写版，5 个 Bug 已修，学习注释已清理 |
| `src/agent/tools.py` | ✅ 修复 | Review fix 已应用（宪宪-豆包） |
| `tests/test_agent/test_agent.py` | ✅ 修复 | 测试适配手写 LangGraph（移除了 `create_agent` mock） |
| `tests/test_agent/test_tools.py` | ✅ 修复 | 错误信息断言适配 |
| `.learnings/agent-handwritten-qa.md` | ✅ 更新 | 本段即为本次经验记录 |

---

> 下次更新：进入 LangGraph 多智能体模式（Supervisor + Worker）或加 ConversationSummaryMemory。
