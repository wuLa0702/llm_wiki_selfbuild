# Phase 4.5 — 知识工程增强

> 插入到 Phase 4 和 Phase 5 之间，原 Phase 5（UI 美化）后移至 Phase 6
> 日期：2026-07-09

---

## 现状分析结论

| 功能 | 当前状态 | 需要做 |
|------|---------|--------|
| 1. **来源可追溯** | LLM 被提示包含 sources，但 `_write_pages()` 不做后处理验证。~42 页缺少 frontmatter | 注入逻辑 |
| 2. **Embedding** | **不存在**。无向量存储、无 embed 方法、无 schema | 从零搭建 |
| 3. **overview.md 更新** | `_update_overview()` 存在，但 LLM 返回太泛，prompt 需增强 | 修复 prompt |
| 4. **语言感知生成** | prompt 硬编码中文。无配置项 | 配置化 |
| 5. **资料源渐进渲染** | 无 `/wiki/sources` 路由 | 新增 API + 页面 |
| 6. **队列可视化** | API 端点已有，无前端页面 | 新增 HTML 页面 |

---

## Step 1: 来源可追溯（~30min）

### 问题
LLM 生成页面时有时缺 `sources:` frontmatter 字段，`source_overlap` 图信号因此退化。

### 方案
在 `wiki_compiler.py` 的 `_write_pages()` 中，仿照已有的 `_inject_privacy_frontmatter()` 模式添加 `_inject_sources_frontmatter()`。

```python
@staticmethod
def _inject_sources_frontmatter(content: str, source_path: str) -> str:
    """在 YAML frontmatter 中注入 sources: 字段"""
    lines = content.split("\n")
    if len(lines) >= 2 and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                source_ref = f"raw/sources/{source_path}"
                lines.insert(i, f"sources:\n  - {source_ref}")
                break
        return "\n".join(lines)
    # 无 frontmatter → 在前面添加 frontmatter
    source_ref = f"raw/sources/{source_path}"
    return f"---\nsources:\n  - {source_ref}\n---\n\n{content}"
```

在 `_write_pages()` 中调用：

```python
def _write_pages(self, pages, privacy_matches=None, source_path=None):
    for path, page_content in pages.items():
        if source_path:
            page_content = self._inject_sources_frontmatter(page_content, source_path)
        if privacy_matches:
            page_content = self._inject_privacy_frontmatter(page_content, privacy_matches)
        ...
```

### 改动文件
- `src/core/compiler/wiki_compiler.py`: 新增 `_inject_sources_frontmatter()`, 修改 `_write_pages()` 签名和调用
- `ingest()` 调用 `_write_pages()` 时传入 `source_path`

---

## Step 2: Embedding 支持（~2h）

### 方案
- 向量数据库：**Chroma**（`pip install chromadb`，本地持久化，零配置）
- 嵌入提供者：DeepSeek API 的 embedding 端点
- 配置开关：`EMBEDDING_ENABLED=true/false`
- 触发时机：ingest 后自动为新/更新的页面生成 embedding

### 2.1 新增依赖
```
# requirements.txt
chromadb>=0.5.0
```

### 2.2 新增配置
`src/config.py`:
```python
embedding_enabled: bool = False
chroma_persist_dir: str = "chroma_db"
embedding_provider: str = "deepseek"
embedding_dim: int = 1024
```

### 2.3 新增 `src/core/embedding.py`
```python
class EmbeddingEngine:
    """向量嵌入引擎 — Chroma + DeepSeek embedding API"""
    
    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        if not enabled:
            return
        self.client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self.collection = self.client.get_or_create_collection("wiki_pages")
    
    def embed_page(self, path: str, content: str) -> None:
        if not self.enabled:
            return
        embedding = self._get_embedding(content)
        self.collection.upsert(ids=[path], embeddings=[embedding], metadatas=[{"path": path}])
    
    def search(self, query: str, k: int = 10) -> list[dict]:
        if not self.enabled:
            return []
        query_embed = self._get_embedding(query)
        results = self.collection.query(query_embeddings=[query_embed], n_results=k)
        return results
    
    def _get_embedding(self, text: str) -> list[float]:
        """调用 DeepSeek embedding API"""
        ...
```

### 2.4 集成到 ingest 管线
`wiki_compiler.py` — 在 `_write_pages()` 后调用：

```python
if created or updated:
    mark_lint_cache_dirty()
    from src.core.embedding import get_embedding_engine
    engine = get_embedding_engine()
    for p in created + updated:
        content = self._read_wiki_file(p)
        engine.embed_page(p, content)
```

### 2.5 新增 API
```python
@router.post("/v1/search", response_model=SearchResponse)
async def semantic_search(request: SearchRequest):
    """语义搜索（需要 EMBEDDING_ENABLED=true）"""
```

### 改动文件
- `requirements.txt` — +chromadb
- `src/config.py` — +embedding 配置项
- `src/core/embedding.py` — **新文件**
- `src/core/compiler/wiki_compiler.py` — ingest 后触发 embedding
- `src/models/common.py` — +SearchRequest/SearchResponse

---

## Step 3: overview.md 修复（~20min）

### 问题
`_update_overview()` 的 prompt 效果不佳，LLM 输出太通用。需要确认 `chat()` 调用的实际行为（`prompt` vs `system_prompt` 的优先级）。

### 方案
- 确认 `chat()` 方法实际行为（prompt 作为 human message，system_prompt 作为 system message — index_content 应被发送）
- 如果没问题：改进 prompt 使输出更具体
- 如果确实丢失：修复 prompt 组装

### 改动文件
- `src/core/compiler/wiki_compiler.py`: `_update_overview()` prompt 增强

---

## Step 4: 语言感知生成（~30min）

### 4.1 新增配置
`src/config.py`:
```python
output_language: str = "zh"  # zh / en
```

### 4.2 动态注入
在 `wiki_compiler.py` 的 `ingest()`, `ingest_simple()`, `_update_overview()`, `query()` 中读取 `settings.output_language` 并追加语言指令到 prompt：

```python
lang_instruction = {
    "zh": "请使用中文回答，标题和文件名使用中文。英文专业术语保留原文。",
    "en": "Please respond in English. Use English titles and filenames.",
}.get(settings.output_language, "")
```

### 改动文件
- `src/config.py` — +output_language
- `src/core/compiler/wiki_compiler.py` — 4 处注入语言指令

---

## Step 5: 资料源渐进渲染（~45min）

### 5.1 API
`src/api/routes/misc.py`:
```python
@router.get("/v1/sources")
async def list_sources(page: int = 1, per_page: int = 50):
    """分页列出 raw/sources/ 下的文件（名称、大小、修改时间）"""
```

### 5.2 页面
`src/api/templates/sources.html` — IntersectionObserver 滚动加载

`src/api/routes/wiki.py`:
```python
@router.get("/wiki/sources")
async def wiki_sources():
    """资料源浏览器 — 渐进滚动渲染"""
    return HTMLResponse(Path("src/api/templates/sources.html").read_text(...))
```

### 改动文件
- `src/api/routes/wiki.py` — +`/wiki/sources`
- `src/api/routes/misc.py` — +`/v1/sources`
- `src/api/templates/sources.html` — **新文件**

---

## Step 6: 队列可视化（~45min）

### 方案
队列 API 已存在（`/v1/ingest/queue/status`, `/cancel/{job_id}`, `/retry/{job_id}`），只需前端页面。

`src/api/templates/queue.html`:
```
┌──────────────────────────────────────────────┐
│  活动面板 — 摄入队列                          │
│                                              │
│  [████████████████░░░░░░░░] 65% (13/20)      │
│                                              │
│  ● 处理中: entities/python.md                │
│  ● 排队 (3): import.md, nlp.md, ai.md       │
│  ✕ 失败 (2): large_file.md, bad_format.md    │
│  ✓ 完成 (8)                                  │
│                                              │
│  [取消] [重试] [清除已完成]                    │
└──────────────────────────────────────────────┘
```

每 3 秒自动 poll `/v1/ingest/queue/status`。

### 改动文件
- `src/api/routes/wiki.py` — +`/wiki/queue`
- `src/api/templates/queue.html` — **新文件**

---

## 实施顺序

```
Step 1 (来源可追溯)  ← 独立，先做
Step 3 (overview 修复)  ← 独立，先做
Step 4 (语言感知)  ← 独立
Step 2 (embedding)  ← 最重，后做
Step 5 (渐进渲染)  ← 等 Step 2 完成
Step 6 (队列可视化)  ← 随时可做
```

## 文件总览

| Step | 新建 | 修改 |
|------|------|------|
| 1 | — | `wiki_compiler.py` |
| 2 | `core/embedding.py`, `models/common.py` 扩展 | `config.py`, `wiki_compiler.py`, `requirements.txt` |
| 3 | — | `wiki_compiler.py` |
| 4 | — | `config.py`, `wiki_compiler.py` |
| 5 | `templates/sources.html` | `wiki.py`, `misc.py` |
| 6 | `templates/queue.html` | `wiki.py` |

## 验证

```bash
# Step 1
curl -X POST .../v1/ingest -d '{"source_path":"test.md"}'
# → 生成的页面必须包含 sources: frontmatter

# Step 2
curl .../v1/search?q=Python
# → 返回语义相似的页面

# Step 3
curl .../wiki/overview.md
# → 内容反映最新 wiki 状态

# Step 4
# 设置 output_language=en 重新 ingest → 页面标题为英文

# Step 5
curl .../wiki/sources
# → 渐进渲染的资料源列表

# Step 6
curl .../wiki/queue
# → 实时队列活动面板
```
