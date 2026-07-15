# LLM Wiki — 技术栈

> 日期：2026-07-13 | Python 3.14.5

---

## 后端

| 类别 | 技术 | 版本 | 用途 |
|------|------|:----:|------|
| **Web 框架** | FastAPI | 0.135 | API 路由 + Jinja2 模板渲染 |
| **ASGI** | Uvicorn | 0.49 | 开发/生产服务器 |
| **模板** | Jinja2 | 3.1 | 服务端 HTML 模板（继承 + htmx 双模式） |
| **数据校验** | Pydantic v2 | 2.13 | 请求/响应模型 |
| **配置** | pydantic-settings | 2.14 | `.env` 环境变量管理 |

| 类别 | 技术 | 用途 |
|------|------|------|
| **LLM 调用** | LangChain | OpenAI 兼容协议封装（DeepSeek / 豆包 Ark） |
| **Provider** | deepseek-v4-flash (默认) | 快速推理 |
| **Provider** | 豆包 Ark | 备选 |

| 类别 | 技术 | 用途 |
|------|------|------|
| **数据库** | SQLite3 | wiki_pages / page_links / operation_log |
| **存储** | Markdown 文件 | `wiki/` 目录下的 `.md` 文件 |
| **原始资料** | `raw/sources/` | 只读原始文件 |

| 类别 | 技术 | 用途 |
|------|------|------|
| **Markdown** | python-markdown | 服务端 md→HTML（extra, fenced_code） |
| **图谱** | networkx | 服务端 spring_layout 预计算节点坐标 |
| **社区检测** | python-louvain | Louvain 社区聚类 |
| **关键词搜索** | rank-bm25 | BM25 全文检索 |
| **向量搜索** | ChromaDB + sentence-transformers | 语义搜索（可选，默认关闭） |
| **文件解析** | python-docx, pptx, pypdf, openpyxl | 导入 Word/PPT/PDF/Excel |

| 类别 | 技术 | 用途 |
|------|------|------|
| **任务队列** | TaskQueue | 异步任务（ingest、图谱重建） |
| **文件监听** | SourceWatcher | raw/sources/ 轮询自动导入（默认关闭） |

---

## 前端

| 类别 | 技术 | 加载方式 | 用途 |
|------|------|:----:|------|
| **CSS** | 原生 CSS 变量体系 | 内联 | 暗色/亮色主题、三区布局、排版 |
| **JS** | 原生 ES5 | 内联 | 主题管理、树形面板、知识树、活动轮询 |
| **局部刷新** | htmx 1.9 | CDN (unpkg) | 图标栏导航无全页刷新 |
| **代码高亮** | highlight.js 11.9 | CDN (cdnjs) | 代码块语法高亮 |
| **Markdown 渲染** | marked.js | CDN (jsdelivr) | 文件 tab 内 md 文件渲染 |
| **图谱** | Sigma.js v3 | CDN (esm.sh) | WebGL 知识图谱渲染 |
| **图结构** | Graphology 0.26 | CDN (esm.sh) | 图数据模型 |
| **图布局** | graphology-layout-forceatlas2 | CDN (esm.sh) | ForceAtlas2 布局算法 |
| **Wikilink 预览** | 原生 JS | 内联 | hover 弹出摘要卡片 |

---

## 部署

| 方式 | 命令 |
|------|------|
| **开发** | `uvicorn src.main:app --reload` |
| **生产** | `python run.py` |
| **打包** | PyInstaller `wiki.spec` → 236MB 轻量版（排除了 torch/transformers） |

---

## 不使用的技术

| 技术 | 原因 |
|------|------|
| React / Vue / Svelte | Jinja2 + htmx 够用，零构建 |
| TypeScript | 保持简单，ES5 兼容 |
| webpack / Vite | 零构建步骤 |
| Tailwind CSS | 自定义 CSS 变量体系更可控 |
| Redis / PostgreSQL | 单机 Wiki，SQLite 够用 |
| Docker | 未到需要容器化的阶段 |
