/**
 * LLM Wiki — 基础 JavaScript
 * 主题管理 / 树形面板 / 知识树加载 / 活动状态 / 工具函数
 */

/* ========================= 图标栏激活 ========================= */
function setActiveIcon(btn) {
  document.querySelectorAll('.icon-bar-item').forEach(function(el) { el.classList.remove('active'); });
  btn.classList.add('active');
}

function initActiveIcon() {
  var path = window.location.pathname;
  document.querySelectorAll('.icon-bar-item').forEach(function(el) {
    var dp = el.getAttribute('data-path');
    if (dp === path) el.classList.add('active');
    // 子路径匹配
    if (path.startsWith(dp + '/') && dp !== '/wiki') el.classList.add('active');
  });
}

/* ========================= 主题 ========================= */
function updateThemeIcon() {
  var isDark = document.documentElement.classList.contains("dark");
  var icons = document.querySelectorAll("#theme-icon, #settingsThemeIcon");
  icons.forEach(function(el) {
    el.textContent = isDark ? "☀️" : "🌙";
  });
}

function initTheme() {
  if (localStorage.getItem("theme") === "dark") {
    document.documentElement.classList.add("dark");
  }
  updateThemeIcon();
}

function toggleTheme() {
  var html = document.documentElement;
  html.classList.toggle("dark");
  localStorage.setItem("theme", html.classList.contains("dark") ? "dark" : "light");
  updateThemeIcon();
}

/* ========================= 工具 ========================= */
function debounce(fn, delay) {
  var timer = null;
  return function() {
    var args = arguments;
    var ctx = this;
    clearTimeout(timer);
    timer = setTimeout(function() { fn.apply(ctx, args); }, delay);
  };
}

function escapeHtml(str) {
  if (!str) return "";
  var div = document.createElement("div");
  div.appendChild(document.createTextNode(str));
  return div.innerHTML;
}

function formatBytes(bytes) {
  if (bytes == null || bytes === 0) return "0 B";
  var units = ["B", "KB", "MB", "GB"];
  var i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + " " + units[i];
}

function showToast(message) {
  var existing = document.querySelector(".toast");
  if (existing) existing.remove();
  var toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(function() { toast.remove(); }, 3000);
}

/* ========================= 最近访问 ========================= */
function recordPageVisit(path) {
  if (!path) return;
  try {
    var recent = JSON.parse(localStorage.getItem("wikiRecentPages") || "[]");
    // 去重：移除同路径
    recent = recent.filter(function(p) { return p !== path; });
    recent.unshift(path);
    if (recent.length > 5) recent = recent.slice(0, 5);
    localStorage.setItem("wikiRecentPages", JSON.stringify(recent));
  } catch(e) {}
}

function renderRecentPages(container) {
  try {
    var recent = JSON.parse(localStorage.getItem("wikiRecentPages") || "[]");
    if (!recent.length) return;
    var html = '<div class="tree-section"><div class="tree-section-title" onclick="toggleTreeSection(this)">';
    html += '<span class="chevron open">&#9654;</span> ';
    html += '<span style="color:var(--accent-blue);">🕐 最近访问 (' + recent.length + ')</span></div>';
    html += '<ul class="tree-items">';
    for (var i = 0; i < recent.length; i++) {
      var isActive = window.location.pathname === "/wiki/" + encodeURIComponent(recent[i]);
      html += '<li class="tree-item"><a href="/wiki/' + encodeURIComponent(recent[i]) + '"' + (isActive ? ' class="active"' : "") + ">" + escapeHtml(recent[i]) + "</a></li>";
    }
    html += "</ul></div><div class=\"tree-section\"><div class=\"icon-bar-divider\" style=\"margin:0.25rem 0;\"></div></div>";
    container.insertAdjacentHTML("afterbegin", html);
  } catch(e) {}
}

// 页面加载时记录当前访问
(function() {
  var match = window.location.pathname.match(/^\/wiki\/(.+)/);
  if (match) {
    recordPageVisit(decodeURIComponent(match[1]));
  }
})();

/* ========================= 本地搜索缓存 ========================= */
var _pageCache = [];

/* ========================= 知识树加载 ========================= */
async function loadTree() {
  var container = document.getElementById("tree-content");
  if (!container) return;

  try {
    var res = await fetch("/v1/pages");
    if (!res.ok) throw new Error("HTTP " + res.status);
    var data = await res.json();
    var pages = data.pages || [];
    _pageCache = pages; // 缓存到本地，供搜索使用

    if (!pages.length) {
      container.innerHTML = '<div class="empty-state" style="padding:1.5rem"><p class="text-sm">知识库为空<br><a href="/wiki/import">去导入资料</a></p></div>';
      document.getElementById("tree-stats").textContent = "共 0 页";
      return;
    }

    // 最近访问（顶部）
    renderRecentPages(container);

    // 按类型分组
    var groups = {};
    var typeLabels = { entity: "实体", concept: "概念", source: "来源", query: "问答", other: "其他" };
    var typeOrder = ["entity", "concept", "source", "query", "other"];
    var total = 0;

    for (var i = 0; i < pages.length; i++) {
      var p = pages[i];
      var type = p.page_type || "other";
      if (!groups[type]) groups[type] = [];
      groups[type].push(p);
      total++;
    }

    var html = "";
    for (var t = 0; t < typeOrder.length; t++) {
      var type = typeOrder[t];
      var items = groups[type];
      if (!items || !items.length) continue;
      html += '<div class="tree-section">';
      var sectionKey = "wikiSection_" + (typeLabels[type] || type);
      var sectionState = "collapsed";
      try { sectionState = localStorage.getItem(sectionKey) || "collapsed"; } catch(e) {}
      var isCollapsed = sectionState === "collapsed";
      html += '<div class="tree-section-title" onclick="toggleTreeSection(this)" data-section="' + (typeLabels[type] || type) + '">';
      html += '<span class="chevron ' + (isCollapsed ? "" : "open") + '">&#9654;</span> ';
      html += '<span class="section-label">' + (typeLabels[type] || type) + ' (' + items.length + ')</span>';
      html += '</div>';
      html += '<ul class="tree-items ' + (isCollapsed ? "hidden" : "") + '">';
      for (var j = 0; j < items.length; j++) {
        var path = items[j].path || items[j].name || "";
        var isActive = window.location.pathname === "/wiki/" + encodeURIComponent(path);
        html += '<li class="tree-item"><a href="/wiki/' + encodeURIComponent(path) + '"' + (isActive ? ' class="active"' : "") + ">" + escapeHtml(path) + "</a></li>";
      }
      html += "</ul></div>";
    }

    container.innerHTML = html;
    document.getElementById("tree-stats").textContent = "共 " + total + " 页";

    // 异步获取断链数
    fetch("/v1/lint?semantic=false")
      .then(function(r) { return r.json(); })
      .then(function(d) {
        var broken = (d.broken_links || []).length;
        var el = document.getElementById("tree-stats");
        if (el) el.textContent = "共 " + total + " 页 · " + broken + " 断链";
      })
      .catch(function() {});
  } catch (err) {
    container.innerHTML = '<div class="error-state" style="padding:1rem"><p>加载失败</p><button class="btn btn-sm" onclick="loadTree()">重试</button></div>';
  }
}

function toggleTreeSection(el) {
  var chevron = el.querySelector(".chevron");
  var items = el.nextElementSibling;
  if (chevron) chevron.classList.toggle("open");
  if (items) items.classList.toggle("hidden");
  // 使用 data-section 属性（与 loadTree 用同样的 key 算法）
  var sectionName = el.getAttribute("data-section");
  if (sectionName) {
    var key = "wikiSection_" + sectionName;
    var isHidden = items && items.classList.contains("hidden");
    try { localStorage.setItem(key, isHidden ? "collapsed" : "open"); } catch(e) {}
  }
}

function switchTab(tab) {
  // 切换 tab 高亮
  document.querySelectorAll(".tree-tab").forEach(function(t) {
    t.classList.toggle("active", t.getAttribute("data-tab") === tab);
  });
  // 显示/隐藏内容
  document.getElementById("tab-knowledge").style.display = tab === "knowledge" ? "" : "none";
  document.getElementById("tab-files").style.display = tab === "files" ? "" : "none";
  // 懒加载文件树
  if (tab === "files") loadFileTree();
  // 保存当前 tab
  try { localStorage.setItem("wikiTreeTab", tab); } catch(e) {}
}

async function loadFileTree() {
  var container = document.getElementById("file-tree-content");
  if (!container) return;

  try {
    var res = await fetch("/v1/file-tree");
    var tree = await res.json();
    var html = renderFileTree(tree, "");
    container.innerHTML = '<div class="file-tree-rendered">' + html + '</div>';
  } catch(err) {
    container.innerHTML = '<div class="error-state" style="padding:1rem"><p>加载失败</p></div>';
  }
}

function renderFileTree(tree, prefix, depth) {
  depth = depth || 0;
  var html = '<ul class="tree-items" style="padding-left:0;">';
  // 目录排前面，文件排后面，各自按字母排序
  var keys = Object.keys(tree).sort(function(a, b) {
    var aIsDir = tree[a].type === "directory";
    var bIsDir = tree[b].type === "directory";
    if (aIsDir && !bIsDir) return -1;
    if (!aIsDir && bIsDir) return 1;
    return a.localeCompare(b);
  });
  for (var i = 0; i < keys.length; i++) {
    var name = keys[i];
    var item = tree[name];
    var fullPath = prefix ? prefix + "/" + name : name;
    if (item.type === "directory") {
      var isExpanded = depth === 0; // 只展开第一级
      var childrenHtml = item.children ? renderFileTree(item.children, fullPath, depth + 1) : "";
      html += '<li class="tree-item">';
      html += '<div class="tree-section-title" onclick="toggleFileSection(this)"><span class="chevron ' + (isExpanded ? 'open' : '') + '">&#9654;</span> 📁 ' + name + '</div>';
      html += '<div class="tree-items ' + (isExpanded ? '' : 'hidden') + '" style="padding-left:1rem;">' + childrenHtml + '</div>';
      html += '</li>';
    } else {
      var icon = name === "schema.md" ? "📋" : name === "purpose.md" ? "🎯" : "📄";
      html += '<li class="tree-item"><a href="#" onclick="event.preventDefault(); openFile(\'' + fullPath + '\')">' + icon + ' ' + name + '</a></li>';
    }
  }
  html += '</ul>';
  return html;
}

function toggleFileSection(el) {
  var chevron = el.querySelector(".chevron");
  var items = el.nextElementSibling;
  if (chevron) chevron.classList.toggle("open");
  if (items) items.classList.toggle("hidden");
}

function openFile(path) {
  fetch("/v1/file-content?path=" + encodeURIComponent(path))
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (data.content !== undefined) {
        var main = document.querySelector(".main-content");
        if (!main) return;
        var breadcrumb = '<nav class="breadcrumb"><a href="/wiki">首页</a><span class="breadcrumb-separator">/</span><span>' + escapeHtml(path) + '</span></nav>';
        if (path.endsWith(".md") && typeof marked !== 'undefined') {
          // 用 marked.js 渲染 markdown
          var html = marked.parse(data.content);
          main.innerHTML = breadcrumb + '<div class="page-content">' + html + '</div>';
          // 代码高亮
          setTimeout(function() {
            document.querySelectorAll('pre code').forEach(function(b) {
              if (typeof hljs !== 'undefined') hljs.highlightElement(b);
            });
          }, 50);
        } else {
          main.innerHTML = breadcrumb + '<pre style="white-space:pre-wrap; word-break:break-word; font-size:0.85rem; line-height:1.5; background:var(--bg-surface); padding:1rem; border-radius:var(--radius-md);">' + escapeHtml(data.content) + '</pre>';
        }
      } else {
        showToast("加载失败");
      }
    })
    .catch(function() { showToast("加载失败"); });
}

/* ========================= 任务队列轮询（完整状态） ========================= */
var STATUS_LABELS = {
  pending: { icon: "⏳", label: "排队中" },
  processing: { icon: "🔄", label: "处理中" },
  done: { icon: "✅", label: "成功" },
  failed: { icon: "❌", label: "失败" },
  cancelled: { icon: "🚫", label: "已取消" },
};

async function pollActivity() {
  try {
    var [statusRes, recentRes] = await Promise.all([
      fetch("/v1/ingest/queue/status"),
      fetch("/v1/ingest/queue/recent?limit=20"),
    ]);
    if (!statusRes.ok || !recentRes.ok) return;
    var status = await statusRes.json();
    var recent = await recentRes.json();

    var pending = status.pending || 0;
    var processing = status.processing || 0;
    var done = status.done || 0;
    var failed = status.failed || 0;
    var total = status.total || 0;

    // ── 顶部状态点 ──
    var dot = document.getElementById("queue-status-dot");
    var title = document.getElementById("task-queue-title");
    if (dot) {
      if (failed > 0) { dot.className = "queue-dot error"; }
      else if (pending > 0 || processing > 0) { dot.className = "queue-dot busy"; }
      else { dot.className = "queue-dot idle"; }
    }
    if (title) {
      if (pending > 0 || processing > 0) title.textContent = "任务队列 · 运行中";
      else if (failed > 0) title.textContent = "任务队列 · " + failed + " 失败";
      else title.textContent = "任务队列";
    }

    // ── 状态摘要 ──
    var summary = document.getElementById("queue-summary");
    if (summary) {
      summary.innerHTML =
        '<span class="queue-stat pending">排队 ' + pending + '</span>' +
        '<span class="queue-stat processing">处理中 ' + processing + '</span>' +
        '<span class="queue-stat done">成功 ' + done + '</span>' +
        '<span class="queue-stat failed">失败 ' + failed + '</span>';
    }

    // ── 渲染任务列表 ──
    var jobs = recent.jobs || [];
    renderQueueActive(jobs);
    renderQueueDone(jobs);
    renderQueueFailed(jobs);

    // ── 原始源文件 ──
    loadRecentSources();
  } catch (e) {}
}

function renderQueueActive(jobs) {
  var container = document.getElementById("queue-active-list");
  if (!container) return;
  var active = jobs.filter(function(j) { return j.status === "pending" || j.status === "processing"; });
  if (!active.length) {
    container.innerHTML = '<div class="queue-empty">暂无活跃任务</div>';
    return;
  }
  var html = "";
  for (var i = 0; i < active.length; i++) {
    var j = active[i];
    var info = STATUS_LABELS[j.status] || { icon: "❓", label: j.status };
    html += '<div class="queue-item">';
    html += '<span class="queue-icon">' + info.icon + '</span>';
    html += '<span class="queue-name" title="' + escapeHtml(j.source_path || "") + '">' + escapeHtml(j.source_path || j.job_id) + '</span>';
    html += '<span class="queue-status">' + info.label + '</span>';
    html += '<span class="queue-actions">';
    html += '<button class="queue-action-btn queue-del" title="删除此记录" onclick="deleteQueueJob(\'' + j.job_id + '\', this)">✕</button>';
    html += '</span>';
    html += '</div>';
  }
  container.innerHTML = html;
}

function renderQueueDone(jobs) {
  var container = document.getElementById("queue-done-list");
  if (!container) return;
  var done = jobs.filter(function(j) { return j.status === "done"; }).slice(0, 5);
  if (!done.length) {
    container.innerHTML = '<div class="queue-empty">暂无</div>';
    return;
  }
  var html = "";
  for (var i = 0; i < done.length; i++) {
    var j = done[i];
    html += '<div class="queue-item queue-done">';
    html += '<span class="queue-icon">✅</span>';
    html += '<span class="queue-name" title="' + escapeHtml(j.source_path || "") + '">' + escapeHtml(j.source_path || j.job_id) + '</span>';
    html += '<span class="queue-extra">' + (j.result_summary || "") + '</span>';
    html += '<span class="queue-actions">';
    html += '<button class="queue-action-btn queue-del" title="删除此记录" onclick="deleteQueueJob(\'' + j.job_id + '\', this)">✕</button>';
    html += '</span>';
    html += '</div>';
  }
  container.innerHTML = html;
}

function renderQueueFailed(jobs) {
  var container = document.getElementById("queue-failed-list");
  if (!container) return;
  var failed = jobs.filter(function(j) { return j.status === "failed"; });
  if (!failed.length) {
    container.innerHTML = '<div class="queue-empty">暂无失败任务</div>';
    return;
  }
  var html = "";
  for (var i = 0; i < failed.length; i++) {
    var j = failed[i];
    var err = j.error || "未知错误";
    if (err.length > 40) err = err.substring(0, 40) + "…";
    html += '<div class="queue-item queue-failed">';
    html += '<span class="queue-icon">❌</span>';
    html += '<span class="queue-name" title="' + escapeHtml(j.error || "") + '">' + escapeHtml(j.source_path || j.job_id) + '</span>';
    html += '<span class="queue-status" style="color:var(--error);">' + escapeHtml(err) + '</span>';
    html += '<span class="queue-actions">';
    html += '<button class="queue-action-btn queue-retry" title="重新处理此文件" onclick="retryFailedJob(\'' + j.job_id + '\', this)">↻</button>';
    html += '<button class="queue-action-btn queue-del" title="删除此记录" onclick="deleteQueueJob(\'' + j.job_id + '\', this)">✕</button>';
    html += '</span>';
    html += '</div>';
  }
  container.innerHTML = html;
}

async function deleteQueueJob(jobId, btn) {
  if (!confirm("确定删除此任务记录？")) return;
  btn.disabled = true;
  try {
    await fetch("/v1/ingest/queue/" + jobId, { method: "DELETE" });
    showToast("已删除");
    pollActivity();
  } catch(e) {
    showToast("删除失败");
    btn.disabled = false;
  }
}

/* ========================= 重试 / 清空 ========================= */
async function retryFailedJob(jobId, btn) {
  btn.disabled = true;
  btn.textContent = "…";
  try {
    var res = await fetch("/v1/ingest/queue/retry/" + jobId, { method: "POST" });
    var data = await res.json();
    if (data.status === "ok") {
      showToast("已重新加入队列");
      setTimeout(pollActivity, 500);
    } else {
      showToast("重试失败");
      btn.disabled = false;
      btn.textContent = "重试";
    }
  } catch(e) {
    showToast("重试失败");
    btn.disabled = false;
    btn.textContent = "重试";
  }
}

async function retryAllFailed() {
  try {
    var res = await fetch("/v1/ingest/queue/failed");
    if (!res.ok) return;
    var data = await res.json();
    var jobs = data.jobs || [];
    if (!jobs.length) { showToast("没有失败任务"); return; }
    var count = 0;
    for (var i = 0; i < jobs.length; i++) {
      try {
        await fetch("/v1/ingest/queue/retry/" + jobs[i].job_id, { method: "POST" });
        count++;
      } catch(e) {}
    }
    showToast("已重试 " + count + " 个任务");
    setTimeout(pollActivity, 500);
  } catch(e) {
    showToast("操作失败");
  }
}

async function clearAllFailed() {
  if (!confirm("确定清空所有失败任务记录？")) return;
  try {
    var res = await fetch("/v1/ingest/queue/failed", { method: "DELETE" });
    var data = await res.json();
    if (data.status === "ok") {
      showToast("已清空 " + data.deleted + " 个失败记录");
      pollActivity();
    }
  } catch(e) {
    showToast("清空失败");
  }
}

/* ========================= 最近导入 ========================= */
async function loadRecentSources() {
  var body = document.getElementById("source-files-body");
  var countEl = document.getElementById("source-files-count");
  if (!body || !countEl) return;
  try {
    var res = await fetch("/v1/sources/tree");
    var treeData = await res.json();
    var tree = treeData.tree || [];

    var items = [];
    function walk(node) {
      if (node.type === "file") {
        items.push(node);
      }
      if (node.children) {
        for (var i = 0; i < node.children.length; i++) {
          walk(node.children[i]);
        }
      }
    }
    for (var i = 0; i < tree.length; i++) walk(tree[i]);

    // 取最近 8 个
    var recent = items.slice(-8).reverse();
    countEl.textContent = recent.length;
    if (!recent.length) {
      body.innerHTML = '<div class="tree-source-item" style="color:var(--text-muted);justify-content:center;">暂无文件</div>';
      return;
    }
    var html = "";
    for (var i = 0; i < recent.length; i++) {
      html += '<div class="tree-source-item">';
      html += '<span class="file-status ok">✅</span>';
      html += '<span class="file-name">' + escapeHtml(recent[i].name) + '</span>';
      html += '</div>';
    }
    body.innerHTML = html;
  } catch(e) {}
}

function toggleTaskQueue(el) {
  var chevron = el.querySelector(".chevron");
  var body = document.getElementById("task-queue-body");
  if (chevron) chevron.classList.toggle("open");
  if (body) body.classList.toggle("hidden");
}

function toggleSourceFiles(el) {
  var chevron = el.querySelector(".chevron");
  var body = document.getElementById("source-files-body");
  if (chevron) chevron.classList.toggle("open");
  if (body) body.classList.toggle("hidden");
}

/* ========================= 搜索下拉（本地即时 + API 补充） ========================= */
var treeSearchInput = document.getElementById("tree-search-input");
var treeSearchResults = document.getElementById("tree-search-results");
if (treeSearchInput && treeSearchResults) {
  var searchTimer = null;
  treeSearchInput.addEventListener("input", function() {
    clearTimeout(searchTimer);
    var q = this.value.trim().toLowerCase();
    if (q.length < 1) { treeSearchResults.classList.add("hidden"); return; }

    // 1. 本地缓存即时过滤（<10ms）
    var localMatches = [];
    if (_pageCache.length > 0) {
      for (var i = 0; i < _pageCache.length; i++) {
        var p = _pageCache[i];
        var path = (p.path || p.name || "").toLowerCase();
        var title = (p.title || "").toLowerCase();
        if (path.indexOf(q) !== -1 || title.indexOf(q) !== -1) {
          localMatches.push(p);
          if (localMatches.length >= 8) break;
        }
      }
    }

    if (localMatches.length > 0) {
      var html = "";
      for (var i = 0; i < localMatches.length; i++) {
        var path = localMatches[i].path || localMatches[i].name || "";
        html += '<a href="/wiki/' + encodeURIComponent(path) + '" class="search-dropdown-item"><span class="search-path">' + escapeHtml(path) + "</span></a>";
      }
      treeSearchResults.innerHTML = html;
      treeSearchResults.classList.remove("hidden");
    } else {
      treeSearchResults.innerHTML = '<div class="search-dropdown-empty">未找到结果</div>';
      treeSearchResults.classList.remove("hidden");
    }

    // 2. 延时后请求 API 补充（带 snippet 的搜索结果）
    searchTimer = setTimeout(function() {
      fetch("/v1/search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, k: 8, method: "hybrid" }),
      })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        if (!data.results || !data.results.length) return;
        var html = "";
        for (var i = 0; i < data.results.length; i++) {
          var r = data.results[i];
          var path = r.path || "";
          if (path.toLowerCase().indexOf(q) !== -1) continue; // 本地已显示
          html += '<a href="/wiki/' + encodeURIComponent(path) + '" class="search-dropdown-item"><span class="search-path">' + escapeHtml(path) + "</span>";
          if (r.snippet) html += '<span class="search-snippet">' + escapeHtml(r.snippet.substring(0, 60)) + "</span>";
          html += "</a>";
        }
        if (html) treeSearchResults.innerHTML = treeSearchResults.innerHTML + html;
      })
      .catch(function() {});
    }, 200);
  });
  document.addEventListener("click", function(e) {
    if (!treeSearchResults.contains(e.target) && e.target !== treeSearchInput) {
      treeSearchResults.classList.add("hidden");
    }
  });
}

/* ========================= 初始化 ========================= */
document.addEventListener("DOMContentLoaded", function() {
  initTheme();
  initActiveIcon();
  loadTree();
  pollActivity();
  setInterval(pollActivity, 10000);

  // 初始加载也检查空侧栏
  var sz = document.getElementById("sidebar-zone");
  if (sz && sz.innerHTML.trim() === "") {
    sz.style.display = "none";
  }

  // 恢复上次的 tab
  try {
    var savedTab = localStorage.getItem("wikiTreeTab") || "knowledge";
    switchTab(savedTab);
  } catch(e) {}
});

// htmx 内容加载后：重新初始化页面级功能
function reinitMainContent() {
  // 代码高亮
  document.querySelectorAll('pre code').forEach(function(block) {
    if (typeof hljs !== 'undefined') hljs.highlightElement(block);
  });
  // TOC 生成（页面内 h1-h3）
  var toc = document.getElementById('toc-list');
  var tocSidebar = document.getElementById('page-toc');
  if (toc && tocSidebar) {
    var headings = document.querySelectorAll('.page-content h1, .page-content h2, .page-content h3');
    if (headings.length >= 2) {
      var contentEl = document.querySelector('.page-content');
      if (contentEl && contentEl.scrollHeight >= 600) {
        var html = '';
        for (var i = 0; i < headings.length; i++) {
          var h = headings[i];
          var level = parseInt(h.tagName[1], 10);
          var id = 'toc-' + i;
          h.setAttribute('id', id);
          var text = h.textContent || '';
          html += '<li class="toc-level-' + level + '"><a href="#' + id + '">' + escapeHtml(text) + '</a></li>';
        }
        toc.innerHTML = html;
        tocSidebar.style.display = 'block';
      }
    }
  }
  // 记录页面访问
  var match = window.location.pathname.match(/^\/wiki\/(.+)/);
  if (match) recordPageVisit(decodeURIComponent(match[1]));
}

document.addEventListener("htmx:afterSwap", function(evt) {
  // 执行页面级内嵌脚本
  var target = evt.detail.target;
  if (target) {
    target.querySelectorAll('script').forEach(function(s) {
      var ns = document.createElement('script');
      if (s.type) ns.type = s.type;
      ns.textContent = s.textContent;
      document.body.appendChild(ns);
      // module 异步执行，不能立即 remove；普通 script 同步完后可安全移除
      if (ns.type !== 'module') {
        ns.parentNode.removeChild(ns);
      }
    });
  }
  reinitMainContent();
  // 侧栏也被 oob 替换了，重新填充知识树
  if (document.getElementById("tree-content")) {
    loadTree();
  }
});
