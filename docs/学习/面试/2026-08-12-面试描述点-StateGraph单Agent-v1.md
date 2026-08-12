# 面试描述点-StateGraph 单 Agent v1

> 📋 **规范**：遵循 `docs/规则/文档治理规则.md`、`docs/规则/面试描述点规则.md`（R0-R5）
> 📌 **更新时间**：2026-08-12
> 📝 **版本变更记录**（永久保存，只追加不删除）：
> | 版本 | 日期 | 具体改动 |
> |------|------|---------|
> | v1 | 2026-08-12 | 初版：手写 LangGraph StateGraph 单 Agent——10 节点编排 + 三层自修正 + HITL 审批 |

> **目录**：§1 总 ｜ §2 分 ｜ §3 流程图 ｜ §4 总 ｜ §5 数据弹药

> **关联**（双向）：`docs/规则/面试描述点规则.md` ｜ `docs/架构/后端架构目录.md`（§3 数据流）｜ `docs/学习/2026-07-27-学习-agent架构图.md`（节点细节）｜ `docs/索引.md`

---

## §1 总（30s）

> "Agent 层是**手写 LangGraph StateGraph**：10 个节点串起感知→规划→记忆→执行四模块。核心不是把逻辑塞进一个 prompt，而是**拆成节点流**——intent 识别、推理、记忆提炼、工具调用校验、HITL 审批、自修正、上下文压缩，每步可观测、可中断、可恢复。"

## §2 分（60-90s）

**① 10 节点编排**：
```
intent_classifier → agent(call_model) → extract_wm → wm_eviction
  → [有工具调用] validate_tool → approve(HITL) → tools → verify_result
     → [结果差] reflect(LLM反思) 回 agent
  → [无工具] summarizer → END
```

**② 三层自修正（手写核心，面试亮点）**：
- **validate_tool**：步数熔断（防死循环）+ 工具调用去重
- **verify_result**：结果质量校验（不满足标准不往下走）
- **reflect**：LLM 反思错误 → 回 agent 重推理
- 追问点：「为什么三层？」→ 工具层/结果层/推理层各自兜底，避免"只重试工具却不管结果对不对"

**③ HITL 审批**：
- 工具风险分级：只读工具（requires_approval=False）放行，风险工具 `interrupt()` 暂停
- 前端回传 approval → `Command(resume=...)` 恢复；拒绝 → 注入 ToolMessage 回 agent
- 追问点：「中断后状态一致性？」→ MemorySaver checkpointer 每步落库，恢复精确

**④ 状态持久化**：MemorySaver + SQLite 备份（消息/注意力锚/工作记忆/归档摘要）

## §3 流程图

```
用户 → intent 识别 → agent 主推理 → 记忆提炼/淘汰
  → 工具调用？→ 校验(熔断+去重) → HITL 审批 → 执行工具 → 结果校验
  → 差？→ LLM 反思 → 回 agent → 无工具 → 摘要压缩 → END
  （全程 MemorySaver 落库，可中断可恢复）
```

## §4 总（20s）

> "手写 StateGraph 的核心是**把 Agent 行为工程化**：节点拆开、可观测、可中断、可恢复。三层自修正证明我不只调 prompt，而是设计容错链路。这是从'调模型'到'做系统'的分水岭。"

## §5 数据弹药

| 数据 | 值 | commit |
|------|-----|--------|
| 节点 | 10 个 | `planning/graph.py` |
| 自修正 | 三层（熔断/校验/反思）| `d3342d8` |
| 持久化 | MemorySaver + SQLite | store.py |
| 模块化 | 四层重构 | `364b870` |

> 📌 双向链接：节点细节 `docs/学习/2026-07-27-学习-agent架构图.md`；模块化 `docs/学习/2026-07-28-学习-agent模块化架构.md`。
