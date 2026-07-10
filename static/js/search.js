/**
 * LLM Wiki — 搜索下拉
 * 导航栏搜索：防抖 300ms，按类型分组结果
 */

(function() {
  'use strict';

  var input = document.getElementById('nav-search');
  var dropdown = document.getElementById('search-results');
  if (!input || !dropdown) return;

  var debounceTimer = null;

  input.addEventListener('input', function() {
    clearTimeout(debounceTimer);
    var query = input.value.trim();
    if (query.length < 1) {
      dropdown.classList.add('hidden');
      return;
    }
    debounceTimer = setTimeout(function() { doSearch(query); }, 300);
  });

  input.addEventListener('focus', function() {
    if (input.value.trim().length > 0) {
      dropdown.classList.remove('hidden');
    }
  });

  document.addEventListener('click', function(e) {
    if (!dropdown.contains(e.target) && e.target !== input) {
      dropdown.classList.add('hidden');
    }
  });

  // 键盘导航
  input.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
      dropdown.classList.add('hidden');
      return;
    }
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      var items = dropdown.querySelectorAll('.search-dropdown-item');
      if (items.length === 0) return;
      var current = dropdown.querySelector('.search-dropdown-item.active');
      var idx = -1;
      if (current) {
        current.classList.remove('active');
        for (var i = 0; i < items.length; i++) {
          if (items[i] === current) { idx = i; break; }
        }
      }
      var next = e.key === 'ArrowDown' ? idx + 1 : (idx > 0 ? idx - 1 : items.length - 1);
      if (next >= items.length) next = 0;
      if (next < 0) next = items.length - 1;
      items[next].classList.add('active');
      items[next].scrollIntoView({ block: 'nearest' });
      return;
    }
    if (e.key === 'Enter') {
      var active = dropdown.querySelector('.search-dropdown-item.active');
      if (active) {
        e.preventDefault();
        window.location.href = active.getAttribute('href');
      }
    }
  });

  function doSearch(query) {
    dropdown.innerHTML = '<div class="search-dropdown-empty" style="padding:0.5rem;"><div class="spinner" style="width:20px;height:20px;margin:0 auto;"></div></div>';
    dropdown.classList.remove('hidden');

    fetch('/v1/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query, k: 10, method: 'hybrid' }),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
      if (!data.results || data.results.length === 0) {
        dropdown.innerHTML = '<div class="search-dropdown-empty">未找到相关页面</div>';
        return;
      }

      // 按类型分组
      var groups = {};
      var typeLabels = { entity: '📄 实体', concept: '💡 概念', source: '📦 资料', query: '❓ 问答', other: '📄 其他' };
      for (var i = 0; i < data.results.length; i++) {
        var r = data.results[i];
        var type = r.metadata && r.metadata.page_type ? r.metadata.page_type : 'other';
        if (!groups[type]) groups[type] = [];
        groups[type].push(r);
      }

      var typeOrder = ['entity', 'concept', 'source', 'query', 'other'];
      var html = '';
      for (var t = 0; t < typeOrder.length; t++) {
        var type = typeOrder[t];
        var items = groups[type];
        if (!items || !items.length) continue;
        html += '<div style="padding:0.4em 0.75em 0.2em; font-size:0.75rem; color:var(--text-muted);">' + (typeLabels[type] || type) + ' (' + items.length + ')</div>';
        for (var i = 0; i < items.length; i++) {
          var path = items[i].path || '';
          var snippet = items[i].snippet || '';
          html += '<a href="/wiki/' + encodeURIComponent(path) + '" class="search-dropdown-item"><span class="search-path">' + escapeHtml(path) + '</span>';
          if (snippet) {
            html += '<span class="search-snippet">' + escapeHtml(snippet.substring(0, 80)) + '</span>';
          }
          html += '</a>';
        }
      }

      dropdown.innerHTML = html;
    })
    .catch(function(err) {
      dropdown.innerHTML = '<div class="search-dropdown-error">搜索暂不可用</div>';
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }
})();
