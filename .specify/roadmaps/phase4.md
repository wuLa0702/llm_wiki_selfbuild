# Phase 4 — 知识图谱（完整）+ 批量导入 + MCP Server

> **状态**：⬜ 未开始
> **对标**：nashsu v0.4-v0.5
> **前置**：Phase 3 完成（WikiGraph + Query + 静态 Lint + Source 监听 + Token 追踪）
>
> 完整路线图：[roadmap.md](roadmap.md)
> 自检报告：[roadmap-phase4-selfcheck.md](roadmap-phase4-selfcheck.md)

---

## 目标

Phase 3 完成了图结构的**确定性基础**（WikiGraph 邻接表）。Phase 4 在这基础上做三层升级：

1. **图算法层**：4-signal 关联度模型 + Louvain 社区检测 + 洞察引擎
2. **工程层**：文件夹批量导入 + 持久化摄入队列 + 密码保护
3. **集成层**：MCP Server → 外部 AI Agent 可查询 Wiki

### 面试可讲

- "我只用一个 LLM 调用做了语义 Lint——批量检测所有页面的矛盾和知识缺口"
- "4-signal 模型把来源重叠作为最强关联信号（权重×4.0），比纯 wikilinks 解析更有信息量"
- "MCP Server 让 Claude Code 可以直接搜索我的 wiki——面试时可以实时演示"
- "密码保护不是拦截内容生成，而是按标记限制访问——和 Phase 2 的隐私模型一致的哲学"

---

## 依赖链

```
Phase 3 产物（WikiGraph + 静态 Lint + SearchTool + Ingest 稳定）
        │
        ▼
第一步：4-Signal 知识图谱        ← src/core/graph.py（增强）— 图算法层
        │
        ▼
第二步：Louvain 社区检测         ← src/core/community.py（新）— 聚类分析
        │
        ▼
第三步：图谱洞察引擎             ← src/core/insights.py（新）— 惊奇连接 + 知识空白
        │
        ▼
第四步：图谱可视化 HTML          ← static/graph.html（新）— 交互图谱
        │
        ▼
第五步：LLM 语义 Lint            ← src/core/linter.py（增强）— 矛盾 + 缺口 + 浅页
        │
        ▼
第六步：密码保护                 ← src/core/auth.py（新）— API 中间件
        │
        ▼
第七步：持久化摄入队列           ← src/core/ingest_queue.py（新）
        │
        ▼
第八步：文件夹导入               ← src/core/importer.py（新）
        │
        ▼
第九步：MCP Server               ← src/mcp_server.py（新）— Agent 集成

并行支线（不阻塞主干）:
  密码保护 ← 独立模块，可任何时候开发
  MCP Server ← 依赖 API 稳定即可开始
```

---

## 第一步：4-Signal 知识图谱

> **自检说明**：nashsu 的核心差异化——不是简单链接解析，是 4 信号加权关联度模型。

**文件：** `src/core/graph.py`（增强）

### 1.1 四信号模型定义

```python
# 信号权重（来自 nashsu 设计 + 我们的调整）
SIGNAL_WEIGHTS = {
    "direct_link": 3.0,    # [[wikilinks]] 直接相连
    "source_overlap": 4.0, # 共享同一原始 source 文件（最强信号）
    "adamic_adar": 1.5,    # 共享共同邻居，按邻居度加权
    "type_affinity": 1.0,  # 同类型页面加分
}
```

- [ ] 在 `WikiGraph` 中新增 `class RelevanceSignal`：
  - `compute_all()` → 遍历所有节点对，计算 4 个信号的加权总分
  - `direct_link_score()` → 基于已有邻接表（Phase 3 已完成）
  - `source_overlap_score()` → 读取页面的 YAML frontmatter 中 `sources` 字段，统计共同来源数量
  - `adamic_adar_score()` → 对邻居集合计算 Adamic-Adar 指数：`sum(1/log(deg(n)))` over common neighbors
  - `type_affinity_score()` → 从 `WikiRepository` 获取页面类型，同类型 +1.0

- [ ] 存储方式：不实时计算全部 N² 对（1000 页 = 500k 对，可接受），缓存到 SQLite：
  ```sql
  CREATE TABLE IF NOT EXISTS graph_relevance (
      source_path TEXT NOT NULL,
      target_path TEXT NOT NULL,
      total_score REAL NOT NULL,
      direct_link REAL DEFAULT 0,
      source_overlap REAL DEFAULT 0,
      adamic_adar REAL DEFAULT 0,
      type_affinity REAL DEFAULT 0,
      PRIMARY KEY (source_path, target_path)
  );
  ```

### 1.2 查询接口

- [ ] `WikiGraph.related_pages(path: str, limit: int = 20) -> list[dict]`：
  ```python
  def related_pages(self, path: str, limit: int = 20) -> list[dict]:
      """返回与指定页面最相关的 N 个页面（按 total_score 降序）"""
  ```

### 验证

- [ ] 新 ingest 一个源文件 → 相关页面的 source_overlap 分数自动更新
- [ ] `related_pages("entities/python.md")` 返回 5-10 个关联页面，按分数降序
- [ ] 分数包含 4 个信号的分项值

---

## 第二步：Louvain 社区检测

> **面试重点**："系统自动发现你的知识聚类——你可能不知道自己读了 20 篇 NLP 论文，但图谱告诉你了。"

**新文件：** `src/core/community.py`

### 2.1 Louvain 算法实现

- [ ] 实现 `class CommunityDetector`：
  ```python
  class CommunityDetector:
      """Louvain 社区检测 — 自动发现知识聚类"""

      def __init__(self, graph: WikiGraph): ...

      def detect(self) -> dict:
          """
          运行 Louvain 算法

          Returns:
              {
                  "communities": {
                      "社区0": {
                          "name": "NLP",        # LLM 自动命名（可选）
                          "members": ["entities/transformer.md", ...],
                          "cohesion": 0.85,      # 内聚度：内部边密度
                          "size": 12,
                      },
                      ...
                  },
                  "orphan_communities": [...],  # 内聚度 < 0.15 的社区
                  "modularity": 0.72,           # 整体模块度
              }
          """
  ```

- [ ] 算法步骤：
  1. 从 `WikiGraph` 的 edges 构建无向加权图（权重 = 4-signal `total_score`）
  2. 运行 Louvain 社区发现（可使用 `networkx.algorithms.community` 或手写）
  3. 计算每个社区的内聚度（内部边数 / 可能的最大边数）
  4. 标记低内聚社区（cohesion < 0.15）

- [ ] 依赖管理：
  - 优先使用 `networkx`（如果已安装）— `community_louvain` 模块
  - 降级：手写简单版 Louvain（两阶段迭代）

### 2.2 社区命名（可选，调用 1 次 LLM）

- [ ] 收集每个社区的 top-5 高频关键词（TF 统计页面标题和正文）
- [ ] 调用 1 次 LLM 为每个社区生成人类可读的名称（如 "NLP 论文"、"编程语言对比"）
- [ ] 这步可选——如果 LLM 调用失败，使用社区编号（"社区 0"、"社区 1"）

### 验证

- [ ] 检测到 2-3 个以上有意义的社区
- [ ] 社区间连接少，社区内连接密集
- [ ] `modularity > 0.3`（模块度 > 0.3 表示有意义的聚类）

---

## 第三步：图谱洞察引擎

> **面试亮点**："系统告诉你'这两个页面看起来不相关，但它们有深层关联'，以及'你在这个领域存在知识空白'。"

**新文件：** `src/core/insights.py`

### 3.1 惊奇连接检测

- [ ] 实现 `def find_surprising_connections(graph, communities) -> list[dict]`：
  ```python
  def find_surprising_connections(graph: WikiGraph, community_result: dict) -> list[dict]:
      """
      发现"惊奇连接"——跨社区边、跨类型边、中心节点与边缘节点的耦合

      Returns:
          [
              {
                  "source": "entities/python.md",
                  "target": "concepts/design_patterns.md",
                  "reason": "跨社区连接：'编程语言' → '软件架构'",
                  "surprise_score": 0.85,
                  "connection_type": "cross_community",
              },
              ...
          ]
      """
  ```

- [ ] 三种惊奇模式：
  1. **跨社区边**（weight=0.5）：图算法认为它们属于不同社区，但它们之间有直接链接
  2. **跨类型边**（weight=0.3）：entity ↔ concept 之间的链接（同一类型内链接预期之内，跨类型是发现）
  3. **中心↔边缘耦合**（weight=0.2）：高度节点连接到低度节点（"你深入阅读了一个小众话题"）

### 3.2 知识空白检测

- [ ] 实现 `def find_knowledge_gaps(graph, community_result) -> list[dict]`：
  ```python
  def find_knowledge_gaps(graph: WikiGraph, community_result: dict) -> list[dict]:
      """
      发现知识空白——孤立节点、稀疏社区、桥节点

      Returns:
          [
              {
                  "type": "isolated",  # isolated / sparse_community / bridge
                  "node": "concepts/forgotten.md",
                  "description": "此页面未被任何其他页面引用",
                  "suggestion": "考虑合并到相关主题或删除",
              },
              ...
          ]
      """
  ```

- [ ] 三种空白模式：
  1. **孤立节点**（degree ≤ 1）：只有一个连接的页面，可能是"知识孤岛"
  2. **稀疏社区**（cohesion < 0.15）：社区内页面之间连接太少
  3. **桥节点**：连接 3 个以上社区的关键页面，删除它会导致图谱分裂

### 验证

- [ ] 图谱中有明确的跨社区连接 → 被检测为"惊奇连接"
- [ ] 至少 1 个页面入度为 0 → 被检测为"知识空白"

---

## 第四步：图谱可视化 HTML

**新文件：** `static/graph.html`、`static/graph.js`

### 4.1 交互式图谱

- [ ] 基于 `vis.js`（CDN 加载，零构建步骤）或 `sigma.js`
- [ ] 节点和边数据通过 `GET /v1/graph` API 获取（JSON）
- [ ] 视觉编码：
  - 节点大小 ∝ 链接数（√ 缩放）
  - 边粗细 ∝ 4-signal total_score
  - 边颜色：绿色 = 强关联（score > 5），灰色 = 弱关联
  - 节点颜色：按社区分色（谱系色盘，≥8 个社区时用 interpolate）

- [ ] 交互功能：
  - **hover 节点**：高亮邻居，淡化非邻居，显示节点名 + 度
  - **点击节点**：跳转到对应 wiki 页面 `/wiki/{path}`
  - **拖拽布局**：力导向图（vis.js `physics` 启用）
  - **缩放**：鼠标滚轮缩放

### 4.2 图例与控制区

- [ ] 图例面板（可折叠）：
  - 按社区显色
  - 按类型显色（entity / concept / source）
  - 边权重说明（粗线=强关联）

- [ ] 搜索框：输入页面名称 → 高亮匹配节点 + 居中显示
- [ ] "Reset View" 按钮 → 恢复初始布局

### 4.3 API 接入

- [ ] `GET /v1/graph` — 返回图谱 JSON 数据
  ```json
  {
    "nodes": [
      {"id": "entities/python.md", "label": "Python", "type": "entity",
       "community": 0, "degree": {"in": 5, "out": 3}, "relevance_score": 8.5}
    ],
    "edges": [
      {"source": "entities/python.md", "target": "concepts/ai.md",
       "weight": 7.2, "signals": {"direct_link": 3.0, "source_overlap": 4.0, "adamic_adar": 0, "type_affinity": 0.2}}
    ],
    "communities": [
      {"id": 0, "name": "NLP", "cohesion": 0.85, "size": 12},
      {"id": 1, "name": "编程语言", "cohesion": 0.72, "size": 8}
    ],
    "insights": {
      "surprising_connections": [...],
      "knowledge_gaps": [...]
    }
  }
  ```

- [ ] `GET /v1/insights` — 只返回洞察数据（惊奇连接 + 知识空白）

### 验证

- [ ] 打开 `static/graph.html` → 加载图谱
- [ ] 打开 `/wiki/graph` → 嵌入到 Wiki 页面的图谱
- [ ] 点击节点 → 跳转到对应 wiki 页面
- [ ] 图谱显示社区色块

---

## 第五步：LLM 语义 Lint

> **自检说明**：静态 Lint（Phase 3）零成本但只能做格式检查。语义 Lint 用 1 次 LLM 调用做：矛盾检测 + 知识缺口识别 + 浅页标记。
>
> **成本控制**：只调用 1 次 LLM（不是每页 1 次），批量传入所有页面信息。

**文件：** `src/core/linter.py`（增强）

### 5.1 LLM 语义检测

- [ ] 新增 `check_semantic()` 方法：
  ```python
  def check_semantic(self) -> dict:
      """
      调用 LLM 做语义检测（仅一次调用）

      输入：所有页面的 title + type + 摘要（前 200 字）
      输出：JSON 结构

      Returns:
          {
              "contradictions": [
                  {"page_a": "entities/xxx.md", "page_b": "entities/yyy.md",
                   "claim_a": "...", "claim_b": "...", "description": "矛盾描述"}
              ],
              "knowledge_gaps": [
                  {"topic": "Transformer 变体", "mentioned_in": ["entities/xxx.md"],
                   "description": "多处提及但无独立页面"}
              ],
              "shallow_pages": [
                  {"page": "concepts/zzz.md", "reason": "内容过短，仅 50 字",
                   "suggestion": "补充内容或合并到相关页面"}
              ],
          }
      """
  ```

### 5.2 LLM Prompt

**文件：** `src/llm/prompts.py` — 新增 `SYSTEM_PROMPT_LINT_SEMANTIC`

```python
SYSTEM_PROMPT_LINT_SEMANTIC = """你是一个 Wiki 知识库审计员。你的任务是检测页面间的语义问题。

## 检测范围

1. **矛盾检测**：两个页面之间是否存在冲突的主张（如页面 A 说"Python 是动态类型"，页面 B 说"Python 是静态类型"）
2. **知识缺口**：哪些概念在多个页面中被频繁提及但缺少独立页面
3. **浅页面**：哪些页面内容过短或信息量不足，不足以独立成页

## 输入格式

你将收到所有页面的标题、类型和内容摘要（前 200 字）。

## 输出格式（JSON）

{
  "contradictions": [...],
  "knowledge_gaps": [...],
  "shallow_pages": [...]
}

## 原则

- 只标记明确的问题，不确定不标记（减少误报）
- 每个问题附带来源页面路径，方便定位
- 对 contradiction 标注置信度：high / low
"""
```

### 5.3 整合到 Lint API

- [ ] `GET /v1/lint?semantic=true` — 运行语义 Lint（调用 1 次 LLM）
- [ ] 语义 Lint 结果缓存 1 小时（不每次刷新都调 LLM）

### 验证

- [ ] 语义 Lint 检测到已知的矛盾（如有）
- [ ] 调用次数 = 1 次 LLM（不论页面数量）
- [ ] 结果包含 contradictions、knowledge_gaps、shallow_pages 三个数组

---

## 第六步：密码保护

> **背景**：Phase 2 设计了 `visibility: restricted` 的 frontmatter 标记，当时约定密码验证在 Phase 4 实现。
> **哲学**：不拦截内容生成，只限制访问——和 Phase 2 隐私模型一致的"全量生成 + 按标记限制"原则。

**新文件：** `src/core/auth.py`

### 6.1 密码管理

- [ ] 实现 `class PasswordManager`：
  ```python
  class PasswordManager:
      """密码管理 — 用于保护 restricted 页面"""

      def set_password(self, password: str) -> None:
          """设置/更新 Wiki 访问密码（bcrypt 哈希存储）"""

      def verify(self, password: str) -> bool:
          """验证密码"""

      def is_protected(self) -> bool:
          """是否已设置密码"""

      def clear(self) -> None:
          """清除密码（恢复公开访问）"""
  ```

- [ ] 密码存储到 SQLite（`wiki_settings` 表）：
  ```sql
  CREATE TABLE IF NOT EXISTS wiki_settings (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL
  );
  ```
  - key = `"access_password"`，value = bcrypt 哈希

### 6.2 API 端点

- [ ] `POST /v1/auth/password` — 设置密码
  ```json
  {"password": "my-secret"}
  ```

- [ ] `POST /v1/auth/verify` — 验证密码（返回 token）
  ```json
  {"token": "session-xxx", "expires_at": "2026-08-07T15:00:00"}
  ```

- [ ] `POST /v1/auth/clear` — 清除密码

### 6.3 API 中间件

- [ ] FastAPI 中间件 `RestrictedPageMiddleware`：
  - 拦截 `GET /v1/pages/{path}` 和 `GET /wiki/{path}`
  - 检查目标页面的 frontmatter 中 `visibility: restricted`
  - 如果是 restricted 且未验证密码 → 返回 `{"status": "locked", "message": "此页面为私人内容，需要密码验证"}`
  - 验证通过 → 正常返回内容

- [ ] 验证状态通过 cookie 或 JWT token 维持（本阶段用简单 token，Phase 5 UI 美化为登录页面）

### 验证

- [ ] 设置密码后 → 访问 `visibility: restricted` 的页面 → 返回 locked
- [ ] 验证密码后 → 可正常访问 restricted 页面
- [ ] 公开页面（无 visibility 字段或 `visibility: public`）→ 不需要密码
- [ ] 密码 bcrypt 哈希存储，数据库泄露也无法还原

---

## 第七步：持久化摄入队列

> **背景**：当前 ingest 是同步的——每次调用 POST /v1/ingest 直接阻塞返回。批量导入时（文件夹导入）必须串行排队。

**新文件：** `src/core/ingest_queue.py`

### 7.1 队列管理

- [ ] 实现 `class IngestQueue`：
  ```python
  class IngestQueue:
      """持久化摄入队列 — 串行处理 + 崩溃恢复"""

      def __init__(self, db_path: str = "wiki.db"): ...

      def enqueue(self, source_path: str, context: dict | None = None) -> str:
          """加入队列，返回 job_id"""

      def process_next(self) -> dict | None:
          """处理队列中下一个任务（串行）"""

      def status(self, job_id: str) -> dict:
          """查询任务状态"""

      def cancel(self, job_id: str) -> bool:
          """取消待处理的任务"""

      def retry(self, job_id: str) -> bool:
          """重试失败的任务"""

      def progress(self) -> dict:
          """返回队列进度：{total, processed, failed, pending}"""

      @staticmethod
      def _worker():
          """后台线程：不断 process_next"""
  ```

- [ ] SQLite 存储：
  ```sql
  CREATE TABLE IF NOT EXISTS ingest_queue (
      job_id TEXT PRIMARY KEY,
      source_path TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',  -- pending / processing / done / failed / cancelled
      context TEXT,               -- JSON，存储文件夹信息等上下文
      error TEXT,                 -- 失败时的错误信息
      created_at TEXT NOT NULL DEFAULT (datetime('now')),
      updated_at TEXT NOT NULL DEFAULT (datetime('now'))
  );
  ```

- [ ] 崩溃恢复：服务启动时检查是否有 `processing` 状态的任务 → 标记为 `pending` 重新处理

### 7.2 进度查询 API

- [ ] `GET /v1/ingest/queue/status` — 队列状态（总任务数、已完成、失败、进行中）
- [ ] `POST /v1/ingest/queue/cancel/{job_id}` — 取消任务
- [ ] `POST /v1/ingest/queue/retry/{job_id}` — 重试失败任务

### 验证

- [ ] 加入 5 个文件 → 队列依次串行处理，不并行
- [ ] 中断服务 → 重启后未完成的任务自动恢复为 pending
- [ ] 取消任务 → 不再处理
- [ ] 失败任务 → 可单独重试

---

## 第八步：文件夹导入

> **背景**：你不可能一篇一篇调 API。批量导入时，文件夹路径结构本身就提供了分类上下文。
> nashsu 会把文件夹名作为 LLM 的"这堆文件是关于 X 主题的"上下文。

**新文件：** `src/core/importer.py`

### 8.1 导入器

- [ ] 实现 `class FolderImporter`：
  ```python
  class FolderImporter:
      """文件夹导入 — 递归扫描 + 队列 + 上下文注入"""

      def __init__(self, sources_dir: str = "raw/sources"): ...

      def import_folder(self, folder_path: str, recurse: bool = True) -> dict:
          """
          导入文件夹

          1. 扫描目录下所有 .md / .txt / .pdf 文件
          2. 文件夹名作为上下文注入 ingest prompt：
             - "这个文件夹是关于 'LLM 论文' 的"
          3. 所有文件加入 IngestQueue
          4. 返回导入摘要

          Args:
              folder_path: 文件夹路径（相对于 raw/sources/ 或绝对路径）
              recurse: 是否递归子目录

          Returns:
              {"total": 12, "enqueued": 12, "skipped": 0, "queue_id": "xxx"}
          """
  ```

- [ ] 文件夹名作为 LLM 上下文：在 Step 1 的 prompt 中注入 `folder_context`
  ```python
  folder_context = f"该文件位于「{folder_name}」目录下，请关注与此主题相关的实体和概念。"
  ```

### 8.2 API 端点

- [ ] `POST /v1/ingest/folder` — 批量导入文件夹
  ```json
  {
    "folder_path": "raw/sources/llm-papers",
    "recurse": true
  }
  ```

### 验证

- [ ] 导入一个含 5 个文件的文件夹 → 5 个任务全部进入队列
- [ ] 生成页面中实体/概念的提取质量因文件夹上下文而提升（对比不加上下文的结果）
- [ ] 子目录中的文件也被正确导入

---

## 第九步：MCP Server

> **面试亮点**："这是我的 MCP Server——任何支持 MCP 协议的 AI Agent（Claude Code、Cursor）都能直接搜索我的 wiki。"

**新文件：** `src/mcp_server.py`

### 9.1 MCP 协议实现

- [ ] 基于 `mcp` Python SDK（`pip install mcp`）实现 MCP Server
- [ ] 定义工具列表：

| 工具 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `wiki_search` | 全文搜索 | `query: str` | 匹配页面列表 + 摘要 |
| `wiki_read` | 读取页面内容 | `path: str` | Markdown 内容 |
| `wiki_list` | 列出页面 | `type: str` | 页面路径列表 |
| `wiki_graph` | 图谱数据 | 无 | 图谱 JSON |
| `wiki_lint` | 健康检查 | 无 | Lint 报告 |
| `wiki_stats` | 知识库统计 | 无 | 页面数/类型分布 |
| `wiki_related` | 关联页面 | `path: str` | 4-signal 关联页面 |
| `wiki_insights` | 洞察数据 | 无 | 惊奇连接 + 知识空白 |

### 9.2 启动与配置

- [ ] MCP Server 作为独立进程运行（或集成到 FastAPI 的子进程）
- [ ] 启动命令：`python src/mcp_server.py`
- [ ] 通过 stdio 传输（MCP 标准协议）
- [ ] 配置文件 `.claude/mcp.json` 自动生成（可选）

### 9.3 集成测试

- [ ] 启动 MCP Server → 用 `mcp-cli` 测试每个工具
- [ ] Claude Code 可直接搜索 wiki："搜索我的 wiki，有哪些页面关于 Transformer"

### 验证

- [ ] `wiki_search("Transformer")` 返回匹配页面
- [ ] `wiki_read("entities/Transformer.md")` 返回页面内容
- [ ] `wiki_list("concept")` 返回所有概念页面
- [ ] `wiki_related("entities/Transformer.md")` 返回 4-signal 关联页面

---

## 验证标准（端到端）

```bash
# 1. 知识图谱完整
curl http://localhost:8000/v1/graph
# → 含 nodes、edges、communities、insights 四个字段

# 2. 图谱洞察
curl http://localhost:8000/v1/insights
# → {"surprising_connections": [...], "knowledge_gaps": [...]}

# 3. 语义 Lint
curl "http://localhost:8000/v1/lint?semantic=true"
# → {"contradictions": [...], "knowledge_gaps": [...], "shallow_pages": [...]}

# 4. 密码保护
curl http://localhost:8000/v1/pages/concepts/emotion.md
# → {"status": "locked", "message": "此页面为私人内容"}

# 5. 文件夹导入
curl -X POST http://localhost:8000/v1/ingest/folder \
  -H "Content-Type: application/json" \
  -d '{"folder_path": "raw/sources/my-papers", "recurse": true}'
# → {"total": 8, "enqueued": 8}

# 6. 摄入队列状态
curl http://localhost:8000/v1/ingest/queue/status
# → {"total": 8, "processed": 3, "failed": 0, "pending": 5}

# 7. MCP Server 工具列表
# 在 Claude Code 中: /mcp list-tools
# → wiki_search, wiki_read, wiki_list, wiki_graph, wiki_lint, wiki_stats, wiki_related, wiki_insights

# 8. 所有现有测试通过
pytest
```

---

## 预估时间

| 步骤 | 内容 | 预估天数 | LLM 调用 |
|------|------|---------|:--------:|
| 第一步 | 4-Signal 知识图谱 | 2-3 天 | 0 |
| 第二步 | Louvain 社区检测 | 1-2 天 | 0（可选：1 次命名）|
| 第三步 | 图谱洞察引擎 | 1-2 天 | 0 |
| 第四步 | 图谱可视化 HTML | 1-2 天 | 0 |
| 第五步 | LLM 语义 Lint | 1-2 天 | 1 次 |
| 第六步 | 密码保护 | 1 天 | 0 |
| 第七步 | 持久化摄入队列 | 2-3 天 | 0 |
| 第八步 | 文件夹导入 | 1-2 天 | 0 |
| 第九步 | MCP Server | 2-3 天 | 0 |
| **合计** | | **12-18 天** | **仅 1 次** |

> Phase 4 是**图算法密集**阶段，但 9 步中只有 1 步（语义 Lint）需要 LLM 调用。其余全部是确定性算法或协议实现。
