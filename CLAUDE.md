# LLM Wiki — 项目说明书

## 项目概述
LLM Wiki 是一个知识沉淀管理系统。基于 Karpathy 的 LLM Wiki 理念，将原始资料"编译"为结构化 Wiki 知识库。

## 技术栈
- Python 3.11+
- FastAPI（API 框架）
- LangChain（仅模型调用封装层）
- SQLite（元数据存储）
- Markdown 文件（Wiki 内容存储）

## 项目结构
```
llm-wiki/
├── raw/          # 原始素材（只读）
├── wiki/         # LLM 维护的知识层
├── static/       # 前端静态资源（图谱可视化等）
├── src/          # Python 代码
│   ├── main.py   # FastAPI 入口
│   ├── core/     # 核心逻辑
│   ├── tools/    # Agent 工具（权限校验严格）
│   ├── llm/      # LLM 接入封装
│   └── db/       # SQLite 元数据层
├── tests/        # 测试
├── .specify/     # 设计规格
└── .learnings/   # 学习笔记
```

## 核心约束
1. raw/ 目录只读，任何 Agent 不能修改 raw/ 下的文件
2. Agent 只能写入 wiki/ 目录
3. 所有工具调用必须做路径前缀校验（防越权）
4. 优先更新现有 Wiki 页面，禁止随意新建重复页面

## 命名规范
- 文件/函数：snake_case
- 类：PascalCase
- API 路由：/v1/ 前缀

## 开发命令
```bash
# 安装依赖
pip install -r requirements.txt

# 启动服务
uvicorn src.main:app --reload

# 运行测试
pytest
```


<!-- CAT-CAFE-GOVERNANCE-START -->
> Pack version: 1.4.1 | Provider: claude

## Clowder AI Governance Rules (Auto-managed)

### Hard Constraints (immutable)
- **Clowder AI runtime ports**: frontend 3003 and API 3004 are reserved by Clowder AI. Avoid using these ports for this project's dev servers.
- **Redis port 6399** is Clowder AI's production Redis. Never connect to it from external projects. Use 6398 for dev/test.
- **No self-review**: The same individual cannot review their own code. Cross-family review preferred.
- **Identity is constant**: Never impersonate another cat. Identity is a hard constraint.

### Collaboration Standards
- A2A handoff uses five-tuple: What / Why / Tradeoff / Open Questions / Next Action
- Vision Guardian: Read original requirements before starting. AC completion ≠ feature complete.
- Review flow: quality-gate → request-review → receive-review → merge-gate
- Skills are available via symlinked cat-cafe-skills/ — load the relevant skill before each workflow step
- Shared rules: See cat-cafe-skills/refs/shared-rules.md for full collaboration contract

### Quality Discipline (overrides "try simplest approach first")
- **Bug: find root cause before fixing**. No guess-and-patch. Steps: reproduce → logs → call chain → confirm root cause → fix
- **Uncertain direction: stop → search → ask → confirm → then act**. Never "just try it first"
- **"Done" requires evidence** (tests pass / screenshot / logs). Bug fix = red test first, then green

### Knowledge Engineering
- Documents use YAML frontmatter (feature_ids, topics, doc_kind, created)
- Three-layer info architecture: CLAUDE.md (≤100 lines) → Skills (on-demand) → refs/
- Backlog: BACKLOG.md (hot) → Feature files (warm) → raw docs (cold)
- Feature lifecycle: kickoff → discussion → implementation → review → completion
- SOP: See docs/SOP.md for the 6-step workflow
<!-- CAT-CAFE-GOVERNANCE-END -->
