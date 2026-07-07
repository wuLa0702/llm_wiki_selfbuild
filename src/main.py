"""
LLM Wiki — FastAPI 服务入口
"""
import os
import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from src.core.logging_config import configure_logging, get_logger
from src.core.models import IngestRequest, IngestResponse, QueryRequest, QueryResponse
from src.core.privacy import PrivacyManager
from src.core.wiki_compiler import CompilerError, WikiCompiler
from src.db.repository import WikiRepository
from src.llm.adapter import LLMError
from src.tools.read_tool import ReadTool

configure_logging()
logger = get_logger("main")

app = FastAPI(
    title="LLM Wiki API",
    description="知识沉淀管理系统",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("LLM Wiki API 启动 | version=0.1.0")


@app.get("/")
async def root():
    logger.debug("root endpoint 被调用")
    return {"message": "LLM Wiki is running", "version": "0.1.0"}


@app.get("/health")
async def health():
    logger.debug("health endpoint 被调用")
    return {"status": "ok"}


@app.post("/v1/ingest", response_model=IngestResponse)
async def ingest(request: IngestRequest):
    """Ingest 一个源文件到 Wiki 知识库"""
    logger.info("POST /v1/ingest | source_path=%s", request.source_path)

    compiler = WikiCompiler()
    try:
        result = compiler.ingest(request.source_path)
        return result
    except CompilerError as e:
        logger.warning("Ingest failed: %s", e)
        return JSONResponse(
            status_code=404,
            content={"error": "Source not found", "detail": str(e), "code": "NOT_FOUND"},
        )
    except LLMError as e:
        logger.error("Ingest failed (LLM): %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": "LLM call failed", "detail": str(e), "code": "LLM_ERROR"},
        )
    except Exception as e:
        logger.error("Ingest failed (unexpected): %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal error", "detail": str(e), "code": "INTERNAL"},
        )


@app.post("/v1/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """查询 Wiki 知识库，返回带 [[引用]] 的综合回答"""
    logger.info("POST /v1/query | question=%s archive=%s", request.question, request.archive)

    compiler = WikiCompiler()
    try:
        result = compiler.query(request.question, archive=request.archive)
        return QueryResponse(
            answer=result.get("answer", ""),
            sources=result.get("sources", []),
            confidence=result.get("confidence", "low"),
            gaps=result.get("gaps", []),
            archived=result.get("archived"),
        )
    except LLMError as e:
        logger.error("Query 失败 (LLM): %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": "LLM call failed", "detail": str(e), "code": "LLM_ERROR"},
        )
    except Exception as e:
        logger.error("Query 失败 (unexpected): %s", e)
        return JSONResponse(
            status_code=500,
            content={"error": "Internal error", "detail": str(e), "code": "INTERNAL"},
        )


@app.get("/v1/lint")
async def lint():
    """Check wiki health (to be implemented)"""
    logger.info("GET /v1/lint 被调用（桩代码）")
    return {"message": "Lint endpoint — not yet implemented"}


@app.get("/v1/graph")
async def wiki_graph():
    """返回 Wiki 页面的 wikilinks 关系图（JSON）"""
    logger.info("GET /v1/graph")
    compiler = WikiCompiler()
    return compiler.graph.to_dict()


# ==================================================================
# 隐私规则 API
# ==================================================================


@app.get("/v1/privacy/rules")
async def list_privacy_rules():
    """查看所有隐私规则（含默认 + 用户自定义）"""
    pm = PrivacyManager()
    return {"rules": pm.list_rules()}


@app.post("/v1/privacy/rules")
async def add_privacy_rule(request: Request):
    """添加自定义隐私规则"""
    body = await request.json()
    keyword = body.get("keyword", "").strip()
    category = body.get("category", "general").strip()
    if not keyword:
        return JSONResponse(
            status_code=400,
            content={"error": "keyword is required"},
        )
    pm = PrivacyManager()
    pm.add_rule(keyword, category)
    return {"status": "ok", "keyword": keyword, "category": category}


@app.delete("/v1/privacy/rules/{keyword}")
async def remove_privacy_rule(keyword: str):
    """删除用户自定义规则"""
    if not keyword.strip():
        return JSONResponse(
            status_code=400,
            content={"error": "keyword is required"},
        )
    pm = PrivacyManager()
    pm.remove_rule(keyword.strip())
    return {"status": "ok", "keyword": keyword.strip()}


# ==================================================================
# Wiki 浏览路由
# ==================================================================


def _convert_wikilinks(text: str, existing_pages: set | None = None) -> str:
    """将 [[path|显示名]] 和 [[path]] 转换为 HTML 链接

    Args:
        text: 原始 Markdown 文本
        existing_pages: 已知存在的页面集合，用于判断断链
    """
    def replace(match):
        target = match.group(1).strip()
        display = match.group(2).strip() if match.group(2) else target
        css_class = "wikilink"
        if existing_pages is not None and target not in existing_pages:
            css_class = "wikilink broken"
        return f'<a href="/wiki/{target}" class="{css_class}">{display}</a>'

    return re.sub(r"\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]", replace, text)


def _render_page_html(path: str, content: str, existing_pages: set | None = None) -> str:
    """将 Markdown 内容渲染为完整 HTML 页面"""
    import markdown

    # 转换 [[wikilinks]]
    linked = _convert_wikilinks(content, existing_pages)

    # Markdown → HTML
    body = markdown.markdown(linked, extensions=["extra", "fenced_code"])

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{path}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 2em; line-height: 1.7; }}
  a.wikilink {{ color: #2a5db0; text-decoration: none; border-bottom: 1px dashed #2a5db0; }}
  a.wikilink:hover {{ border-bottom-style: solid; }}
  a.wikilink.broken {{ color: #c0392b; border-bottom: 1px dashed #c0392b; }}
  .breadcrumb {{ color: #888; margin-bottom: 1em; }}
  .breadcrumb a {{ color: #2a5db0; }}
  pre {{ background: #f5f5f5; padding: 1em; border-radius: 4px; overflow-x: auto; }}
  blockquote {{ border-left: 3px solid #ddd; margin-left: 0; padding-left: 1em; color: #666; }}
</style>
</head>
<body>
<div class="breadcrumb"><a href="/wiki">Wiki 首页</a> / {path}</div>
{body}
</body>
</html>"""


@app.get("/wiki", response_class=HTMLResponse)
async def wiki_index():
    """Wiki 首页 — 列出所有页面"""
    reader = ReadTool("wiki")
    repo = WikiRepository()

    # 获取所有 .md 文件
    all_files = []
    for root, dirs, files in os.walk(reader.base_dir):
        for f in files:
            if f.endswith(".md"):
                rel = os.path.relpath(
                    os.path.join(root, f), reader.base_dir
                ).replace("\\", "/")
                all_files.append(rel)

    # 按类型分组
    groups: dict[str, list[str]] = {"entity": [], "concept": [], "source": [], "query": [], "other": []}
    for f in sorted(all_files):
        page = repo.get_page(f)
        ptype = page["page_type"] if page else "other"
        if ptype not in groups:
            ptype = "other"
        groups[ptype].append(f)

    # 渲染分组 HTML（ptype 用复数形式显示）
    categories = [
        ("entity", "实体"),
        ("concept", "概念"),
        ("source", "来源"),
        ("query", "问答"),
        ("other", "其他"),
    ]

    sections = []
    for key, label in categories:
        pages = groups.get(key, groups.get(key[:-1], []))
        if not pages:
            continue
        items = [
            f'<li><a href="/wiki/{p}" class="wikilink">{p}</a></li>'
            for p in pages
        ]
        sections.append(f"<h2>{label} ({len(pages)})</h2><ul>{''.join(items)}</ul>")

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LLM Wiki</title>
<style>
  body {{ font-family: -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 2em; line-height: 1.7; }}
  a.wikilink {{ color: #2a5db0; text-decoration: none; }}
  a.wikilink:hover {{ text-decoration: underline; }}
  ul {{ list-style: none; padding-left: 1em; }}
  li {{ padding: 0.2em 0; }}
  h2 {{ border-bottom: 1px solid #eee; padding-bottom: 0.3em; margin-top: 1.5em; }}
</style>
</head>
<body>
<h1>LLM Wiki 知识库</h1>
<p>共 {len(all_files)} 个页面 · <a href="/wiki/query" class="wikilink">知识问答</a> · <a href="/wiki/graph" class="wikilink">图谱视图</a></p>
{''.join(sections)}
</body>
</html>"""
    return html


@app.get("/wiki/graph", response_class=HTMLResponse)
async def wiki_graph_viz():
    """Wiki 图谱可视化 — 交互式力导向图"""
    return HTMLResponse("""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wiki 图谱 — LLM Wiki</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.6/dist/vis-network.min.js"></script>
<style>
  body { margin: 0; font-family: -apple-system, sans-serif; }
  #toolbar { position: fixed; top: 0; left: 0; right: 0; z-index: 10;
             background: #fff; border-bottom: 1px solid #ddd;
             padding: 8px 20px; display: flex; align-items: center; gap: 16px;
             font-size: 14px; }
  #toolbar a { color: #2a5db0; text-decoration: none; }
  #toolbar a:hover { text-decoration: underline; }
  #stats { color: #888; font-size: 13px; }
  #mynetwork { position: fixed; top: 41px; left: 0; right: 0; bottom: 0; }
  .vis-network:focus { outline: none; }
</style>
</head>
<body>
<div id="toolbar">
  <a href="/wiki">&larr; Wiki 首页</a>
  <span id="stats">加载中...</span>
</div>
<div id="mynetwork"></div>
<script>
fetch('/v1/graph')
  .then(r => r.json())
  .then(data => {
    const typeColors = {
      entity: '#3498db', concept: '#2ecc71', source: '#f39c12',
      query: '#9b59b6', other: '#95a5a6',
    };
    const nodes = data.nodes.map(n => {
      const parts = n.id.split('/');
      const type = parts.length > 1 ? parts[0] : 'other';
      let label = parts.pop().replace(/\\.md$/, '');
      const deg = n.degree.out + n.degree.in;
      const size = Math.max(12, Math.min(40, 8 + deg * 3));
      return {
        id: n.id, label, title: `${n.id}\\n出度: ${n.degree.out} | 入度: ${n.degree.in}`,
        color: { background: typeColors[type] || typeColors.other, border: '#2c3e50' },
        size, borderWidth: 1.5,
        font: { size: 11, color: '#2c3e50' },
        shape: 'dot',
      };
    });
    const edges = data.edges.map(e => ({
      from: e.source, to: e.target,
      arrows: { to: { enabled: true, scaleFactor: 0.5 } },
      color: { color: '#bdc3c7', highlight: '#2a5db0', opacity: 0.5 },
      width: 1,
    }));

    const s = data.stats;
    document.getElementById('stats').textContent =
      `${s.total_nodes} 个页面 · ${s.total_edges} 条链接 · 平均度 ${s.avg_degree.toFixed(1)}`;

    const container = document.getElementById('mynetwork');
    const visNodes = new vis.DataSet(nodes);
    const visEdges = new vis.DataSet(edges);
    const network = new vis.Network(container, { nodes: visNodes, edges: visEdges }, {
      physics: { solver: 'forceAtlas2Based', forceAtlas2Based: { springLength: 200, springConstant: 0.02 } },
      interaction: { hover: true, tooltipDelay: 200 },
      edges: { smooth: { type: 'continuous' } },
    });

    let selectedId = null;
    network.on('click', function(params) {
      if (params.nodes.length) {
        window.location.href = '/wiki/' + params.nodes[0];
      } else if (selectedId) {
        network.selectNodes([]);
        selectedId = null;
      }
    });
    network.on('hoverNode', function(params) {
      selectedId = params.node;
      document.body.style.cursor = 'pointer';
    });
    network.on('blurNode', function() {
      document.body.style.cursor = 'default';
    });
  });
</script>
</body>
</html>""")

@app.get("/wiki/query", response_class=HTMLResponse)
async def wiki_query():
    """Wiki 知识问答 — 前端查询界面"""
    return HTMLResponse("""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>知识问答 — LLM Wiki</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 720px; margin: 0 auto; padding: 2em; line-height: 1.7; }
  a { color: #2a5db0; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .header { margin-bottom: 1.5em; color: #888; font-size: 14px; }
  .header a { color: #2a5db0; }
  .input-row { display: flex; gap: 8px; margin-bottom: 1.5em; }
  .input-row input { flex: 1; padding: 10px 14px; font-size: 15px; border: 1px solid #ddd; border-radius: 6px; outline: none; }
  .input-row input:focus { border-color: #2a5db0; box-shadow: 0 0 0 2px rgba(42,93,176,0.1); }
  .input-row button { padding: 10px 24px; font-size: 15px; background: #2a5db0; color: #fff; border: none; border-radius: 6px; cursor: pointer; }
  .input-row button:hover { background: #1d4a8e; }
  .input-row button:disabled { background: #95a5a6; cursor: not-allowed; }
  .options { margin-bottom: 1em; font-size: 13px; color: #666; }
  .options label { cursor: pointer; }
  .options input { margin-right: 4px; }
  .answer-box { border: 1px solid #e0e0e0; border-radius: 8px; padding: 1.2em 1.5em; margin-top: 0.5em; min-height: 60px; display: none; }
  .answer-box.show { display: block; }
  .answer-box.loading { display: flex; align-items: center; justify-content: center; color: #888; min-height: 80px; }
  .answer-box.loading::after { content: ''; width: 18px; height: 18px; margin-left: 8px; border: 2px solid #ddd; border-top-color: #2a5db0; border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .answer-box.error { border-color: #e74c3c; background: #fdf0ef; }
  .meta { font-size: 13px; color: #888; margin-top: 1em; padding-top: 0.8em; border-top: 1px solid #eee; }
  .meta span { margin-right: 1em; }
  .conf-high { color: #27ae60; } .conf-medium { color: #f39c12; } .conf-low { color: #e74c3c; }
  .sources { margin-top: 0.8em; }
  .sources a { display: inline-block; margin-right: 0.5em; }
  .gaps { margin-top: 0.5em; font-size: 13px; color: #e67e22; }
  .hint { color: #aaa; font-size: 13px; text-align: center; padding: 2em 0; }
  .archived { color: #27ae60; font-size: 13px; margin-top: 0.5em; }
</style>
</head>
<body>
<div class="header"><a href="/wiki">&larr; Wiki 首页</a></div>

<div class="input-row">
  <input id="queryInput" type="text" placeholder="向知识库提问…" autofocus>
  <button id="queryBtn" onclick="doQuery()">查询</button>
</div>

<div class="options">
  <label><input type="checkbox" id="archiveCheck"> 归档答案到 wiki/queries/</label>
</div>

<div id="answerBox" class="answer-box"></div>
<div id="hint" class="hint">输入问题后点击查询，LLM 将基于 Wiki 知识库回答。</div>

<script>
function doQuery() {
  const q = document.getElementById('queryInput').value.trim();
  if (!q) return;
  const btn = document.getElementById('queryBtn');
  const box = document.getElementById('answerBox');
  const hint = document.getElementById('hint');
  hint.style.display = 'none';
  box.className = 'answer-box loading';
  box.style.display = 'flex';
  box.textContent = '查询中…';
  btn.disabled = true;

  const archive = document.getElementById('archiveCheck').checked;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);

  fetch('/v1/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question: q, archive }),
    signal: controller.signal,
  })
  .then(r => r.json())
  .then(data => {
    clearTimeout(timer);
    if (data.error) { showError(data.error); return; }
    renderAnswer(data);
  })
  .catch(err => {
    clearTimeout(timer);
    if (err.name === 'AbortError') {
      showError('请求超时（10s），LLM 回答较慢，请稍后重试');
    } else {
      showError('网络错误：' + err.message);
    }
  })
  .finally(() => { btn.disabled = false; });
}

function renderAnswer(data) {
  const box = document.getElementById('answerBox');
  const answer = wikilinksToHtml(data.answer || '');
  const conf = data.confidence || 'low';
  const confLabels = { high: '高', medium: '中', low: '低' };
  const confClass = 'conf-' + conf;

  let html = '<div>' + answer + '</div>';
  html += '<div class="meta">';
  html += '<span class="' + confClass + '">置信度: ' + confLabels[conf] + '</span>';
  if (data.sources && data.sources.length) {
    html += '<span>来源: ' + data.sources.map(s =>
      '<a href="/wiki/' + s + '">' + s.split('/').pop().replace(/\\.md$/, '') + '</a>'
    ).join(', ') + '</span>';
  }
  html += '</div>';

  if (data.gaps && data.gaps.length) {
    html += '<div class="gaps">⚠ 知识缺口: ' + data.gaps.join('; ') + '</div>';
  }
  if (data.archived) {
    html += '<div class="archived">✓ 已归档: <a href="/wiki/' + data.archived + '">' + data.archived + '</a></div>';
  }

  box.className = 'answer-box show';
  box.innerHTML = html;
}

function showError(msg) {
  const box = document.getElementById('answerBox');
  box.className = 'answer-box show error';
  box.innerHTML = '<strong>出错了</strong><br>' + msg;
}

function wikilinksToHtml(text) {
  return text.replace(/\\[\\[([^\\]|]+?)(?:\\|([^\\]]+?))?\\]\\]/g, function(match, target, display) {
    const label = display || target;
    return '<a href="/wiki/' + target + '">' + label + '</a>';
  });
}

document.getElementById('queryInput').addEventListener('keydown', function(e) {
  if (e.key === 'Enter') doQuery();
});
</script>
</body>
</html>""")

@app.get("/wiki/{page_path:path}", response_class=HTMLResponse)
async def wiki_page(page_path: str):
    """渲染单个 Wiki 页面，[[双向链接]] 可点击跳转"""
    reader = ReadTool("wiki")

    # 收集所有存在的页面路径，用于标记断链
    existing_pages: set[str] = set()
    for root, dirs, files in os.walk(reader.base_dir):
        for f in files:
            if f.endswith(".md"):
                rel = os.path.relpath(
                    os.path.join(root, f), reader.base_dir
                ).replace("\\", "/")
                existing_pages.add(rel)

    try:
        content = reader.read_file(page_path)
    except FileNotFoundError:
        return JSONResponse(
            status_code=404,
            content={"error": "Page not found", "path": page_path},
        )
    except PermissionError as e:
        return JSONResponse(
            status_code=403,
            content={"error": "Access denied", "detail": str(e)},
        )

    return HTMLResponse(_render_page_html(page_path, content, existing_pages))
