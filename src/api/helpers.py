"""
API 辅助函数

从 main.py 迁移的共享工具函数：权限检查、Wikilinks 渲染、密码管理工厂。
"""
import os
import re

import markdown

from src.core.auth import PasswordManager
from src.db.repository import WikiRepository
from src.tools.read_tool import ReadTool


def _get_pm() -> PasswordManager:
    """获取 PasswordManager 实例"""
    return PasswordManager(WikiRepository())


def _get_token_from_request(request) -> str | None:
    """从请求中提取 token（优先 Authorization header，其次 query param）"""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    token = request.query_params.get("token")
    return token


def _check_page_access(request, page_path: str) -> bool:
    """检查是否有权限访问指定页面

    公开页面始终可访问。
    restricted 页面需要有效 token。

    Returns:
        True 允许访问，False 拒绝
    """
    repo = WikiRepository()
    meta = repo.get_page(page_path)
    if meta is None:
        return True
    visibility = meta.get("visibility", "public")
    if visibility != "restricted":
        return True
    token = _get_token_from_request(request)
    if not token:
        return False
    pm = _get_pm()
    return pm.validate_token(token)


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
    linked = _convert_wikilinks(content, existing_pages)
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
