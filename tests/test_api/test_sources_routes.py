"""
资料来源路由测试 — 路径契约

核心验证：前端文件树返回的 path（raw/sources/xxx）必须能被
file-content / extract-to-wiki / check-changed / delete 等接口正确解析。

背景：2026-08-01 修复前 _list_dir 返回 sources/xxx（相对 raw/），
与后端校验前缀（raw/sources/）不匹配 → 预览/提取/删除全部 403。
"""
import os

import pytest

from src.api.routes import sources as sources_mod
from src.api.routes import purpose as purpose_mod


@pytest.fixture
def patched_dirs(monkeypatch, tmp_path):
    """把数据目录重定向到 tmp_path，构造 raw/sources/test.md"""
    app_dir = str(tmp_path)
    raw = tmp_path / "raw"
    raw.mkdir()
    sources = raw / "sources"
    sources.mkdir()
    (sources / "test.md").write_text("# Test\n\nhello content", encoding="utf-8")
    (sources / "sub").mkdir()
    (sources / "sub" / "nested.md").write_text("# Nested", encoding="utf-8")
    wiki = tmp_path / "wiki"
    wiki.mkdir()

    for mod in (sources_mod, purpose_mod):
        monkeypatch.setattr(mod, "get_app_dir", lambda: app_dir, raising=False)
    monkeypatch.setattr(sources_mod, "get_raw_sources_dir", lambda: str(sources))
    monkeypatch.setattr(purpose_mod, "get_raw_dir", lambda: str(raw))
    monkeypatch.setattr(sources_mod, "get_wiki_dir", lambda: str(wiki))
    monkeypatch.setattr(purpose_mod, "get_wiki_dir", lambda: str(wiki))
    return app_dir, str(sources), str(wiki)


class TestTreePathContract:
    """文件树 path 契约 — tree 返回的 path 必须可被后端接口消费"""

    def test_tree_paths_use_raw_sources_prefix(self, client, patched_dirs):
        """tree 返回的 path 以 raw/sources/ 开头（修复前是 sources/xxx）"""
        resp = client.get("/v1/sources/tree")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_files"] >= 1

        paths = []
        def walk(items):
            for item in items:
                paths.append(item["path"])
                walk(item.get("children", []))
        walk(data["tree"])

        assert any(p == "raw/sources/test.md" for p in paths), f"路径前缀错误: {paths}"
        assert any(p == "raw/sources/sub/nested.md" for p in paths), f"子目录路径错误: {paths}"

    def test_tree_path_roundtrip_file_content(self, client, patched_dirs):
        """tree 返回的 path 直接传给 /v1/file-content 能读到内容"""
        tree = client.get("/v1/sources/tree").json()["tree"]
        assert tree, "tree 不应为空"

        file_path = None
        def walk(items):
            nonlocal file_path
            for item in items:
                if item["type"] == "file":
                    file_path = item["path"]
                    return
                walk(item.get("children", []))
        walk(tree)
        assert file_path, "tree 中没有文件"

        resp = client.get(f"/v1/file-content?path={file_path}")
        assert resp.status_code == 200, f"file-content 返回 {resp.status_code}: {resp.text[:200]}"
        assert "hello content" in resp.json().get("content", "")

    def test_tree_path_roundtrip_check_changed(self, client, patched_dirs):
        """tree 返回的 path 传给 /v1/sources/check-changed 能通过校验"""
        tree = client.get("/v1/sources/tree").json()["tree"]

        file_path = None
        def walk(items):
            nonlocal file_path
            for item in items:
                if item["type"] == "file":
                    file_path = item["path"]
                    return
                walk(item.get("children", []))
        walk(tree)
        assert file_path, "tree 中没有文件"

        resp = client.get(f"/v1/sources/check-changed?path={file_path}")
        assert resp.status_code == 200, f"check-changed 返回 {resp.status_code}: {resp.text[:200]}"
        assert "changed" in resp.json()


class TestResolveSourcePathCompat:
    """_resolve_source_path 容错 — 兼容 sources/xxx 旧格式"""

    def test_accepts_raw_sources_prefix(self, patched_dirs):
        """标准格式 raw/sources/xxx"""
        abs_path, err = sources_mod._resolve_source_path("raw/sources/test.md")
        assert err is None
        assert abs_path is not None and abs_path.endswith("test.md")

    def test_accepts_sources_prefix(self, patched_dirs):
        """兼容旧格式 sources/xxx（tree 修复前的返回值）"""
        abs_path, err = sources_mod._resolve_source_path("sources/test.md")
        assert err is None, f"旧格式应被兼容: {err}"
        assert abs_path is not None and abs_path.endswith("test.md")

    def test_rejects_other_prefix(self, patched_dirs):
        """非 raw/sources 前缀仍然拒绝"""
        _, err = sources_mod._resolve_source_path("wiki/foo.md")
        assert err == 403


class TestDisplayPathMixedSeparators:
    """_resolve_display_path 分隔符一致性 — Path.cwd() 正斜杠 vs join 反斜杠混用"""

    def test_display_path_with_mixed_separators(self, monkeypatch, tmp_path):
        """get_raw_dir 返回正斜杠风格路径时，校验仍应通过（修复前误判 403）"""
        raw = tmp_path / "raw"
        sources = raw / "sources"
        sources.mkdir(parents=True)
        (sources / "x.md").write_text("x", encoding="utf-8")

        # 模拟 Path.cwd() 的正斜杠风格（Windows 上 Path.cwd() 返回正斜杠）
        monkeypatch.setattr(purpose_mod, "get_app_dir", lambda: str(tmp_path).replace("\\", "/"), raising=False)
        monkeypatch.setattr(purpose_mod, "get_raw_dir", lambda: str(raw).replace("\\", "/"), raising=False)
        monkeypatch.setattr(purpose_mod, "get_wiki_dir", lambda: str(tmp_path / "wiki").replace("\\", "/"), raising=False)

        abs_path, err = purpose_mod._resolve_display_path("raw/sources/x.md")
        assert err is None, f"混合分隔符不应误判 403: {err}"
        assert abs_path is not None and os.path.isfile(abs_path)
