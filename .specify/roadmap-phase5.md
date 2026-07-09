# Phase 5 — 搜索增强 + 文档格式 + 向量搜索 + i18n

> **状态**：🟡 方案设计中
> **对标**：nashsu v0.4 搜索体系
> **前置**：Phase 4 完成后（知识图谱 + 批量导入 + MCP + 队列）
>
> 完整路线图：[roadmap.md](roadmap.md)

---

## 目标

Phase 4 完成了知识结构化（图谱 + 社区 + 洞察）。Phase 5 聚焦"怎么把知识找出来"——从 SQLite LIKE 升级为工业级搜索体系，同时拓展文档格式支持。

### 面试定位

> "我的搜索不是 SQL `LIKE`——BM25 做关键词、向量做语义、RRF 融合排序。PPTX/XLSX 说明我有产品思维，i18n 说明我有工程规范意识。"

---

## 已完成基础（Phase 4.5 遗产）

以下功能已在 Phase 4.5 实施完成，是 Phase 5 搜索体系的基础设施：

| 功能 | 文件 | 说明 |
|------|------|------|
| **来源可追溯** | `wiki_compiler.py` | 注入 `sources:` frontmatter，确保每个页面可追溯回 raw source |
| **语言感知生成** | `config.py` + `wiki_compiler.py` | `output_language` 配置项，动态注入中/英文指令到 ingest/query/overview |
| **资料源渐进渲染** | `wiki.py` + `sources.html` | `/wiki/sources` 页面，IntersectionObserver 滚动加载 |
| **队列可视化** | `wiki.py` + `queue.html` | `/wiki/queue` 页面，每 3 秒自动 poll 进度，取消/重试/清除 |
| **overview.md 修复** | `wiki_compiler.py` | prompt 增强，输出更具体的综述 |
| **Embedding 基础** | `embedding.py` + `chroma_db/` | Chroma + DeepSeek embedding，ingest 后自动索引 |

---

## 新增功能总览

| # | 功能 | 难度 | LLM 成本 | 文件 |
|:-:|------|:----:|:--------:|------|
| 1 | **PPTX/XLSX 文档解析** | 中 | 0 | `src/core/parsers/`（新） |
| 2 | **CJK Bigram 分词** | 中 | 0 | `src/core/search/`（新） |
| 3 | **BM25 关键词搜索** | 中 | 0 | `src/core/search/`（新） |
| 4 | **向量语义搜索（强化）** | 中 | 0 | `src/core/embedding.py`（增强） |
| 5 | **RRF 混合搜索融合** | 中 | 0 | `src/core/search/`（新） |
| 6 | **i18n 国际化** | 低 | 0 | `src/i18n/`（新） |

---

## Step 1: PPTX/XLSX 文档解析

> **面试价值**："支持 PPTX/XLSX 解析不是简单的加库——它是产品思维的体现。你的用户不会只传 Markdown。"

### 1.1 文件结构

**新目录：** `src/core/parsers/`

```python
src/core/parsers/
├── __init__.py       # parse_document(path) -> str 统一入口
├── base.py           # BaseParser 抽象类
├── pptx_parser.py    # python-pptx 实现
├── xlsx_parser.py    # openpyxl 实现
└── md_parser.py      # 已有 .md 读取（重构抽取）
```

### 1.2 统一接口

```python
class BaseParser(ABC):
    """文档解析器抽象类"""

    SUPPORTED_EXTENSIONS: list[str] = []

    @abstractmethod
    def parse(self, file_path: str) -> str:
        """解析为纯文本（保留结构化信息如标题层级）"""
        ...

def parse_document(file_path: str) -> str:
    """自动检测扩展名 → 选择对应 Parser → 返回文本"""
```

### 1.3 PPTX 解析要点

- `python-pptx` 遍历 `slide.shapes` 提取文本框文本
- 保留标题层级（slide title → `# `，正文 → 段落）
- 表格提取为 markdown 表格格式
- 忽略图片、图表（仅提取文本）

### 1.4 XLSX 解析要点

- `openpyxl` 遍历 `worksheet.iter_rows()`
- 每个 sheet 用 `## Sheet 名` 分隔
- 行转 markdown 表格

### 1.5 集成到 Ingest

```python
# read_tool.py 新增
def read_file(self, relative_path: str) -> str:
    ext = os.path.splitext(relative_path)[1].lower()
    if ext in {".pptx", ".xlsx", ".ppt", ".xls"}:
        from src.core.parsers import parse_document
        return parse_document(full_path)
    # ... 原有 .md 读取逻辑
```

### 验证

- [ ] `.pptx` 文件 → 解析为 markdown 结构化文本，标题层级正确
- [ ] `.xlsx` 文件 → 每个 sheet 独立段落，表格转为 markdown 表格
- [ ] 解析后的文本通过 ingest 生成 wiki 页面
- [ ] 不支持格式返回友好错误

---

## Step 2: CJK Bigram 分词 + 停用词

> **背景**：当前 `SearchTool` 用 SQLite `LIKE` 搜索，中文只支持"精确子串匹配"——搜"学习"找不到"深度学习"。
> **面试话术**："中文搜索的基本功是分词。`LIKE '%学习%'` 能工作，但 `LIKE '%机器%'` 搜不到'机器学习'。Bigram 把句子切成'机器/器学/学习'，3 个词任意匹配都能命中。"

### 2.1 Bigram 实现

```python
def cjk_bigram(text: str) -> list[str]:
    """
    中文 CJK 二元分词 + 英文空格分词

    "机器学习是什么" → ["机器", "器学", "学习", "习是", "什么"]
    "Python 学习" → ["python", "学习"]
    """
```

- CJK 字符范围：`一-鿿`（中日韩统一表意文字）
- 非 CJK 字符用空格分词 + 小写化
- 停用词过滤：去掉 "的"、"了"、"是"、"在" 等高频无意义词

### 2.2 索引集成

- 在 `WikiRepository` 中新增 `fts_terms` 表：

```sql
CREATE TABLE IF NOT EXISTS fts_terms (
    page_path TEXT NOT NULL,
    term TEXT NOT NULL,
    term_count INTEGER DEFAULT 1,
    PRIMARY KEY (page_path, term)
);
CREATE INDEX idx_fts_term ON fts_terms(term);
```

- 每个页面写入/更新时，对标题+正文做 Bigram 分词，写入 `fts_terms`
- 搜索时对 query 做同样 Bigram → 查 `fts_terms` → 按匹配数排序

### 2.3 停用词表

`src/core/search/stopwords.py`:

```python
STOPWORDS_ZH = {"的", "了", "是", "在", "我", "有", "和", "就", "不", "人",
                "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
                "你", "会", "着", "没有", "看", "好", "自己", "这", "他", "她",
                "它", "们", "那", "什么", "怎么", "为什么", "如何", "哪个"}
```

### 验证

- [ ] `cjk_bigram("机器学习")` → `["机器", "器学", "学习"]`
- [ ] `cjk_bigram("Python 编程")` → `["python", "编程"]`
- [ ] 搜"学习" → 匹配"机器学习"页面
- [ ] 搜"的" → 被停用词过滤，返回空（或提示）

---

## Step 3: BM25 关键词搜索

> **BM25 比 SQLite `LIKE` 强在哪？**
> - `LIKE`：子串匹配，不分词、不计权
> - BM25：**词频（TF）** × **逆文档频率（IDF）** — 词在文档中出现越多越好（TF），在所有文档中出现越少越重要（IDF）
> - 支持标题加权（标题命中得分更高）

### 3.1 实现

使用 `rank_bm25` 库（纯 Python，零依赖）：

```python
from rank_bm25 import BM25Okapi

class BM25Search:
    """BM25 关键词搜索 — 标题加权 + 全文索引"""

    def __init__(self):
        self._index: BM25Okapi | None = None
        self._corpus: list[str] = []
        self._dirty = True  # 页面更新后标记脏，重建索引

    def build_index(self, pages: list[dict]) -> None:
        """从页面列表构建 BM25 索引"""
        corpus = [p["title"] + " " + p["title"] + " " + p["content"] for p in pages]
        tokenized = [cjk_bigram(doc) for doc in corpus]
        self._index = BM25Okapi(tokenized)
        self._dirty = False

    def search(self, query: str, k: int = 10) -> list[dict]:
        """搜索返回 BM25 排序结果"""
        tokenized_query = cjk_bigram(query)
        scores = self._index.get_scores(tokenized_query)
        # 按分数降序取 top-k
        ...
```

### 3.2 生命周期

- 服务启动时构建一次索引（1000 页 < 1s）
- ingest 后标记 `dirty`，下次搜索前重建
- 或增量更新（BM25 不支持增量，简单重建即可）

### 验证

- [ ] 搜"Python" → BM25 排序结果比 SQLite LIKE 更精确（高频词降权）
- [ ] 标题命中 → 排名高于正文命中
- [ ] 1000 页索引重建 < 1s

---

## Step 4: 向量语义搜索（强化）

> **背景**：Phase 4.5 已实现基础的 Chroma + DeepSeek embedding，但仅限于 ingest 后自动索引。
> **强化**：整合到统一的搜索接口，与 BM25 组成混合检索。

### 4.1 API 搜索端点

```python
@router.post("/v1/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    """
    混合搜索：BM25 关键词 + 向量语义，RRF 融合

    Request:
        {"query": "Python 异步编程", "k": 10}

    Response:
        {
            "results": [
                {"path": "entities/python.md", "score": 0.92,
                 "title": "Python", "snippet": "支持 async/await..."},
                ...
            ],
            "total": 3,
            "method": "hybrid"  # bm25 / vector / hybrid
        }
    """
```

### 4.2 整合 EmbeddingEngine

`src/core/embedding.py` 增强：

```python
class EmbeddingEngine:
    def search(self, query: str, k: int = 10) -> list[dict]:
        """语义搜索 — 返回页面路径 + 余弦相似度"""
        ...
```

### 验证

- [ ] `/v1/search?q=Python` 返回 BM25 + 向量混合结果
- [ ] 搜"async" 返回包含"异步"的页面（跨关键词的语义匹配）
- [ ] embedding 配置关闭时，自动降级为纯 BM25

---

## Step 5: RRF 混合搜索融合

> **RRF（Reciprocal Rank Fusion）**：BM25 和向量搜索各自返回排序结果，RRF 将二者的排名融合为一个最终排序。
> **公式**：`RRF_score(d) = 1/(k + r_bm25(d)) + 1/(k + r_vector(d))`

### 5.1 实现

```python
def rrf_fusion(bm25_results: list[dict], vector_results: list[dict],
               k: int = 60, top_n: int = 10) -> list[dict]:
    """
    RRF 融合 BM25 和向量搜索的结果

    Args:
        bm25_results: BM25 返回的 [{"path": "...", ...}]
        vector_results: 向量搜索返回的 [{"path": "...", ...}]
        k: RRF 常数（默认 60）
        top_n: 返回 top-N

    Returns:
        融合排序后的结果列表
    """
    scores: dict[str, float] = defaultdict(float)
    for rank, result in enumerate(bm25_results):
        scores[result["path"]] += 1.0 / (k + rank + 1)
    for rank, result in enumerate(vector_results):
        scores[result["path"]] += 1.0 / (k + rank + 1)
    sorted_paths = sorted(scores, key=scores.get, reverse=True)[:top_n]
    ...
```

### 5.2 搜索策略选择

```python
class SearchEngine:
    """统一搜索入口 — 策略模式"""

    def __init__(self):
        self.bm25 = BM25Search()
        self.vector = EmbeddingEngine()

    def search(self, query: str, method: str = "hybrid") -> list[dict]:
        if method == "bm25":
            return self.bm25.search(query)
        elif method == "vector":
            return self.vector.search(query)
        elif method == "hybrid":
            bm25_results = self.bm25.search(query, k=20)
            vector_results = self.vector.search(query, k=20)
            return rrf_fusion(bm25_results, vector_results, top_n=10)
```

### 验证

- [ ] 纯 BM25 / 纯向量 / 混合 三种模式都可工作
- [ ] 混合模式结果排序优于单模式（recall 更高）
- [ ] embedding 关闭时，混合模式自动降级为纯 BM25

---

## Step 6: i18n 国际化

> **面试话术**："i18n 用配置文件驱动——新增语言只需加一个 YAML 文件，不改代码。这不是翻译，是工程规范。"

### 6.1 文件结构

**新目录：** `src/i18n/`

```python
src/i18n/
├── __init__.py       # gettext() 统一入口
├── zh.yaml           # 中文
├── en.yaml           # 英文
└── README.md         # 维护说明
```

### 6.2 配置驱动

```yaml
# zh.yaml
wiki:
  title: "LLM Wiki 知识库"
  stats:
    total_pages: "共 {count} 个页面"
    entities: "实体"
    concepts: "概念"
    sources: "来源"
  search:
    placeholder: "搜索知识库..."
    no_results: "未找到匹配结果"
  errors:
    not_found: "页面不存在"
    locked: "此页面为私人内容"
```

### 6.3 集成

```python
from src.i18n import gettext as _

def gettext(key: str, **kwargs) -> str:
    """从当前语言的 YAML 读取翻译"""
    lang = settings.output_language or "zh"
    translations = _load_yaml(lang)
    value = _resolve_key(translations, key)
    if kwargs:
        value = value.format(**kwargs)
    return value
```

### 6.4 使用

```python
# 在 API 返回中使用
return {"message": _("wiki.stats.total_pages", count=42)}

# 在模板中使用（Jinja2 可调 Python 函数）
<h1>{{ gettext("wiki.title") }}</h1>
```

### 验证

- [ ] `output_language=zh` → 所有 UI 文字为中文
- [ ] `output_language=en` → 所有 UI 文字为英文
- [ ] 缺失的 key → 返回 key 本身（不崩溃）
- [ ] 新增语言只需加一个 YAML 文件

---

## 实施顺序

```
基础建设（并行推进，互不依赖）:
  Step 1: PPTX/XLSX 解析      ← 独立模块，随时可做
  Step 6: i18n 国际化          ← 独立模块，随时可做

搜索体系（线性依赖）:
  Step 2: CJK Bigram + 停用词  ← 先做（BM25 依赖它做分词）
  Step 3: BM25 关键词搜索      ← 依赖 Step 2
  Step 4: 向量语义搜索（强化）   ← Phase 4.5 已有基础
  Step 5: RRF 混合搜索         ← 依赖 Step 3 + Step 4
```

## 新增文件总览

| Step | 新建 | 修改 |
|------|------|------|
| 1 | `src/core/parsers/__init__.py`, `base.py`, `pptx_parser.py`, `xlsx_parser.py` | `read_tool.py` |
| 2 | `src/core/search/bigram.py`, `stopwords.py` | `repository.py`（+`fts_terms` 表）|
| 3 | `src/core/search/bm25_search.py` | — |
| 4 | — | `embedding.py` 增强 |
| 5 | `src/core/search/engine.py`, `rrf.py` | `main.py`（+`/v1/search`）|
| 6 | `src/i18n/__init__.py`, `zh.yaml`, `en.yaml` | `config.py`（+`i18n_dir`）|
| 测试 | `tests/test_core/test_parsers.py`, `tests/test_search/...` | — |

## 验证

```bash
# Step 1: PPTX 解析
curl -X POST .../v1/ingest -d '{"source_path":"samples/presentation.pptx"}'
# → 成功解析文本，生成 wiki 页面

# Step 2-5: 搜索体系
curl .../v1/search?q=机器学习&method=hybrid
# → BM25 + 向量 RRF 融合，返回相关页面

curl .../v1/search?q=机器学习&method=bm25
# → 纯 BM25

curl .../v1/search?q=async%20programming&method=vector
# → 语义匹配"异步编程"

# Step 6: i18n
curl .../v1/pages
# → output_language=zh 时字段为中文
# → output_language=en 时字段为英文
```
