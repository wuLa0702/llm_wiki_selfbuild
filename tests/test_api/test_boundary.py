"""
Phase 3 后端边界补漏测试

覆盖 TEST-PLAN Phase 3 步骤 3：
1. 特殊字符路径（中文/空格/#）全链路
2. 空文件（size=0 / 空内容）
3. 超大文件（file-content 完整返回，不截断）
4. 路径穿越拒绝（file-content / delete / extract）
5. 并发上传（多线程不丢文件）
"""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from src.api.routes import ingest as ingest_mod
from src.api.routes import sources as sources_mod
from src.api.routes import purpose as purpose_mod


@pytest.fixture
def boundary_dirs(monkeypatch, tmp_path):
    """数据目录重定向，构造特殊字符/空/超大三类边界文件"""
    app_dir = str(tmp_path)
    raw = tmp_path / "raw"
    raw.mkdir()
    sources = raw / "sources"
    sources.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()

    # newline="\n"：避免 Windows 文本模式把 \n 写成 \r\n 导致 size 断言偏差
    (sources / "中文 文档#1.md").write_text("# 中文标题\n\n内容", encoding="utf-8", newline="\n")
    (sources / "empty.md").write_text("", encoding="utf-8", newline="\n")
    (sources / "big.md").write_text("# Big\n\n" + "x" * 1_500_000, encoding="utf-8", newline="\n")

    for mod in (sources_mod, purpose_mod):
        monkeypatch.setattr(mod, "get_app_dir", lambda: app_dir, raising=False)
    monkeypatch.setattr(sources_mod, "get_raw_sources_dir", lambda: str(sources))
    monkeypatch.setattr(purpose_mod, "get_raw_dir", lambda: str(raw))
    monkeypatch.setattr(sources_mod, "get_wiki_dir", lambda: str(wiki))
    monkeypatch.setattr(purpose_mod, "get_wiki_dir", lambda: str(wiki))
    return app_dir, str(sources), str(wiki)


def _collect_paths(tree: list[dict]) -> list[str]:
    paths = []
    for item in tree:
        paths.append(item["path"])
        paths.extend(_collect_paths(item.get("children", [])))
    return paths


class TestSpecialCharPaths:
    """中文 / 空格 / # 文件名：tree → file-content 全链路"""

    def test_tree_returns_special_char_paths(self, client, boundary_dirs):
        data = client.get("/v1/sources/tree").json()
        paths = _collect_paths(data["tree"])
        assert "raw/sources/中文 文档#1.md" in paths, f"特殊字符路径缺失: {paths}"
        assert "raw/sources/empty.md" in paths
        assert "raw/sources/big.md" in paths

    def test_file_content_roundtrip_special_chars(self, client, boundary_dirs):
        resp = client.get("/v1/file-content", params={"path": "raw/sources/中文 文档#1.md"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "# 中文标题\n\n内容"
        assert data["size"] == len("# 中文标题\n\n内容".encode("utf-8"))

    def test_special_char_file_delete(self, client, boundary_dirs):
        resp = client.delete("/v1/sources/delete", params={"path": "raw/sources/中文 文档#1.md"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"
        assert not os.path.exists(os.path.join(boundary_dirs[1], "中文 文档#1.md"))


class TestEmptyFile:
    """空文件：tree size=0、content 为空字符串"""

    def test_empty_file_size_zero_in_tree(self, client, boundary_dirs):
        data = client.get("/v1/sources/tree").json()
        empty = next(i for i in _collect_paths(data["tree"]) if i.endswith("empty.md"))
        # tree item 的 size 字段
        def find(items):
            for item in items:
                if item["path"] == "raw/sources/empty.md":
                    return item
                r = find(item.get("children", []))
                if r:
                    return r
            return None
        item = find(data["tree"])
        assert item is not None
        assert item["size"] == 0

    def test_empty_file_content_returns_empty_string(self, client, boundary_dirs):
        resp = client.get("/v1/file-content", params={"path": "raw/sources/empty.md"})
        assert resp.status_code == 200
        assert resp.json()["content"] == ""
        assert resp.json()["size"] == 0


class TestLargeFile:
    """超大文件：file-content 完整返回（无截断）+ size 正确"""

    def test_large_file_content_not_truncated(self, client, boundary_dirs):
        resp = client.get("/v1/file-content", params={"path": "raw/sources/big.md"})
        assert resp.status_code == 200
        data = resp.json()
        expected_len = len("# Big\n\n" + "x" * 1_500_000)
        assert len(data["content"]) == expected_len, "超大文件内容被截断"
        assert data["size"] == expected_len
        # 首尾完整性抽查
        assert data["content"].startswith("# Big")
        assert data["content"].endswith("x" * 10)


class TestPathTraversal:
    """路径穿越：../ 与绝对路径拒绝"""

    def test_file_content_rejects_dotdot(self, client, boundary_dirs):
        resp = client.get("/v1/file-content", params={"path": "../secrets.txt"})
        assert resp.status_code == 403
        assert resp.json()["error"] == "Access denied"

    def test_file_content_rejects_absolute(self, client, boundary_dirs):
        resp = client.get("/v1/file-content", params={"path": "/etc/passwd"})
        assert resp.status_code == 403

    def test_delete_rejects_dotdot(self, client, boundary_dirs):
        resp = client.delete("/v1/sources/delete", params={"path": "../../outside.md"})
        assert resp.status_code == 403

    def test_extract_rejects_dotdot(self, client, boundary_dirs):
        resp = client.post("/v1/sources/extract-to-wiki",
                           json={"source_path": "../escape.md"})
        assert resp.status_code == 403

    def test_check_changed_rejects_dotdot(self, client, boundary_dirs):
        resp = client.get("/v1/sources/check-changed", params={"path": "../x.md"})
        assert resp.status_code == 403


class TestConcurrentUpload:
    """并发上传：多线程同时 POST upload，文件全部落盘不丢失"""

    @pytest.fixture
    def upload_env(self, monkeypatch, tmp_path):
        sources = tmp_path / "raw" / "sources"
        sources.mkdir(parents=True)

        from src.utils import path_resolver
        monkeypatch.setattr(path_resolver, "get_raw_sources_dir", lambda: str(sources))

        class FakeQueue:
            pass
        monkeypatch.setattr(ingest_mod, "get_ingest_queue", lambda: FakeQueue())

        from src.core.ingest import FolderImporter
        monkeypatch.setattr(
            FolderImporter, "import_folder_async",
            lambda self, *a, **k: {"total": 0, "enqueued": 0, "skipped_unchanged": 0},
        )
        return str(sources)

    def test_concurrent_upload_all_files_saved(self, upload_env):
        from src.main import app

        def upload(i: int) -> dict:
            client = TestClient(app)
            payload = {}
            for j in range(2):
                # httpx files 元组：(filename: str, content: bytes, content_type)
                payload[f"f{j}"] = (f"concurrent_{i}_{j}.md", f"# 并发 {i}-{j}".encode("utf-8"), "text/markdown")
            resp = client.post("/v1/ingest/upload", files=payload)
            return resp.json()

        with ThreadPoolExecutor(max_workers=4) as ex:
            results = list(ex.map(upload, range(4)))

        assert len(results) == 4
        saved_total = sum(r["saved"] for r in results)
        assert saved_total == 8, f"并发上传丢失文件: saved={saved_total}"

        on_disk = sorted(os.listdir(upload_env))
        assert len(on_disk) == 8, f"落盘文件数不符: {on_disk}"
        for i in range(4):
            for j in range(2):
                name = f"concurrent_{i}_{j}.md"
                assert name in on_disk
                with open(os.path.join(upload_env, name), encoding="utf-8") as f:
                    content = f.read()
                assert content == f"# 并发 {i}-{j}"

    def test_upload_rejects_path_traversal_filename(self, upload_env):
        """上传文件名带 ../ 被跳过（不落盘、不计入 saved）"""
        from src.main import app
        client = TestClient(app)
        resp = client.post("/v1/ingest/upload", files={
            "f0": ("../../evil.md", b"# evil", "text/markdown"),
            "f1": ("good.md", b"# good", "text/markdown"),
        })
        data = resp.json()
        assert data["saved"] == 1
        assert not os.path.exists(os.path.join(upload_env, "..", "..", "evil.md"))
        assert os.path.exists(os.path.join(upload_env, "good.md"))
