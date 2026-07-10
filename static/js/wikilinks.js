/**
 * LLM Wiki — Wikilink Hover 预览卡片
 * 鼠标悬浮 [[wikilink]] 时 fetch 摘要并弹出预览
 */

(function() {
  'use strict';

  var previewEl = null;
  var hideTimer = null;
  var activeRequest = null;

  // 创建预览卡片 DOM
  function getPreviewEl() {
    if (!previewEl) {
      previewEl = document.createElement('div');
      previewEl.className = 'preview-card';
      previewEl.style.display = 'none';
      document.body.appendChild(previewEl);
    }
    return previewEl;
  }

  // 显示预览
  function showPreview(target, x, y) {
    var el = getPreviewEl();

    // 加载态
    el.innerHTML = '<div class="preview-card-loader"><div class="skeleton skeleton-row" style="width:70%"><div class="skeleton-pulse"></div></div><div class="skeleton skeleton-row" style="width:50%"><div class="skeleton-pulse"></div></div></div>';
    el.style.display = 'block';
    positionCard(el, x, y);

    // 取消之前的请求
    if (activeRequest) {
      activeRequest.abort();
    }
    var controller = new AbortController();
    activeRequest = controller;

    var targetPath = target.replace(/^\//, '');

    fetch('/v1/pages/' + encodeURIComponent(targetPath) + '?summary=true', {
      signal: controller.signal,
    })
    .then(function(r) {
      if (!r.ok) throw new Error('Not found');
      return r.json();
    })
    .then(function(data) {
      if (controller.signal.aborted) return;

      var title = data.title || data.path || targetPath;
      var pageType = data.page_type || '';
      var content = data.content || data.summary || '';
      var excerpt = content.replace(/<[^>]+>/g, '').substring(0, 120);
      var backlinks = (data.backlinks || []).length;
      var html = '<div class="preview-card-title">' + escapeHtml(title) + '</div>';

      if (pageType) {
        html += '<div class="preview-card-type"><span class="badge badge-' + pageType + '">' + pageType + '</span></div>';
      }
      if (excerpt) {
        html += '<div class="preview-card-excerpt">' + escapeHtml(excerpt) + '</div>';
      }
      html += '<div class="preview-card-meta text-muted">入链: ' + backlinks + ' 页 · 点击跳转 →</div>';

      el.innerHTML = html;
      positionCard(el, x, y);
    })
    .catch(function(err) {
      if (err.name === 'AbortError') return;
      el.innerHTML = '<div class="preview-card-error">预览加载失败</div>';
    });
  }

  function positionCard(el, x, y) {
    var w = 280;
    var h = el.offsetHeight || 120;
    var vw = window.innerWidth;
    var vh = window.innerHeight;

    var left = x + 12;
    var top = y + 12;

    // 不超出右边界
    if (left + w > vw - 8) {
      left = x - w - 12;
    }
    // 不超出下边界
    if (top + h > vh - 8) {
      top = vh - h - 8;
    }
    // 不超出左边界
    if (left < 8) left = 8;
    if (top < 8) top = 8;

    el.style.left = left + 'px';
    el.style.top = top + 'px';
  }

  function hidePreview() {
    if (previewEl) {
      previewEl.style.display = 'none';
    }
  }

  // 延迟隐藏，让鼠标可以移入预览卡片
  function delayedHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(hidePreview, 300);
  }

  // 监听 hover
  document.addEventListener('mouseover', function(e) {
    var link = e.target.closest('.wikilink');
    if (!link) {
      delayedHide();
      return;
    }

    clearTimeout(hideTimer);
    var href = link.getAttribute('href');
    if (!href || !href.startsWith('/wiki/')) return;

    var target = href.replace('/wiki/', '');
    showPreview(target, e.pageX, e.pageY);
  });

  // 预览卡片上 hover 不会隐藏
  document.addEventListener('mouseover', function(e) {
    if (previewEl && previewEl.contains(e.target)) {
      clearTimeout(hideTimer);
    }
  });

  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }
})();
