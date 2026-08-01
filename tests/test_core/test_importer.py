"""
FolderImporter 单元测试 — Phase 4 Step 8
"""
import os

import pytest

from src.core.ingest import FolderImporter


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def sources_dir(tmp_path):
    d = tmp_path / "raw" / "sources"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def importer(sources_dir):
    return FolderImporter(str(sources_dir))


# ============================================================================
# _scan_folder
# ============================================================================


def test_scan_folder_finds_md_files(sources_dir, importer):
    """扫描 .md 文件"""
    (sources_dir / "papers").mkdir()
    (sources_dir / "papers" / "a.md").write_text("# A", encoding="utf-8")
    (sources_dir / "papers" / "b.md").write_text("# B", encoding="utf-8")

    files = importer._scan_folder("papers")
    assert len(files) == 2
    assert "papers/a.md" in files
    assert "papers/b.md" in files


def test_scan_folder_filters_extensions(sources_dir, importer):
    """只保留支持的扩展名"""
    (sources_dir / "papers").mkdir()
    (sources_dir / "papers" / "a.md").write_text("# A")
    (sources_dir / "papers" / "b.txt").write_text("B")
    (sources_dir / "papers" / "c.png").write_text("C")
    (sources_dir / "papers" / "d.docx").write_text("D")  # .docx 不是支持的扩展

    files = importer._scan_folder("papers")
    # 我们的 SUPPORTED_EXTENSIONS 是 {".md", ".txt", ".pdf", ".html", ".csv"}
    assert "papers/a.md" in files
    assert "papers/b.txt" in files
    assert "papers/c.png" not in files
    assert "papers/d.docx" not in files


def test_scan_folder_nonexistent(importer):
    """不存在的文件夹返回空列表"""
    assert importer._scan_folder("nonexistent") == []


def test_scan_folder_recursive(sources_dir, importer):
    """recurse=True 时扫描子目录"""
    (sources_dir / "papers").mkdir()
    (sources_dir / "papers" / "nlp").mkdir()
    (sources_dir / "papers" / "a.md").write_text("# A")
    (sources_dir / "papers" / "nlp" / "b.md").write_text("# B")

    files = importer._scan_folder("papers", recurse=True)
    assert len(files) == 2

    files_no_recurse = importer._scan_folder("papers", recurse=False)
    assert len(files_no_recurse) == 1  # 只有 a.md


def test_scan_folder_skips_hidden(sources_dir, importer):
    """跳过以 . 开头的文件"""
    (sources_dir / "papers").mkdir()
    (sources_dir / "papers" / "a.md").write_text("# A")
    (sources_dir / "papers" / ".hidden.md").write_text("# hidden")

    files = importer._scan_folder("papers")
    assert len(files) == 1
    assert ".hidden.md" not in str(files)


# ============================================================================
# import_folder
# ============================================================================


def test_import_folder_empty(importer):
    """空文件夹返回全 0 统计"""
    result = importer.import_folder("nonexistent")
    assert result["total"] == 0
    assert result["success"] == 0
    assert result["failed"] == 0


def test_import_folder_calls_ingest(sources_dir, importer, mocker):
    """import_folder 对每个文件调用 compiler.ingest"""
    (sources_dir / "papers").mkdir()
    (sources_dir / "papers" / "a.md").write_text("# A")
    (sources_dir / "papers" / "b.md").write_text("# B")

    mock_compiler = mocker.MagicMock()
    mock_compiler.ingest.return_value = {
        "status": "success", "pages_created": ["p1.md"], "pages_updated": [],
    }

    result = importer.import_folder("papers", compiler=mock_compiler)

    assert result["total"] == 2
    assert result["success"] == 2
    assert mock_compiler.ingest.call_count == 2


def test_import_folder_passes_context(sources_dir, importer, mocker):
    """import_folder 传入 folder_context"""
    (sources_dir / "papers").mkdir()
    (sources_dir / "papers" / "a.md").write_text("# A")

    mock_compiler = mocker.MagicMock()
    mock_compiler.ingest.return_value = {"status": "success", "pages_created": [], "pages_updated": []}

    importer.import_folder("papers", compiler=mock_compiler)

    # 验证传入了 folder_context
    call_kwargs = mock_compiler.ingest.call_args[1]
    assert "folder_context" in call_kwargs
    assert "papers" in call_kwargs["folder_context"]


def test_import_folder_skipped_counted(sources_dir, importer, mocker):
    """skipped 状态单独统计"""
    (sources_dir / "data").mkdir()
    (sources_dir / "data" / "a.md").write_text("# A")

    mock_compiler = mocker.MagicMock()
    mock_compiler.ingest.return_value = {"status": "skipped", "pages_created": [], "pages_updated": []}

    result = importer.import_folder("data", compiler=mock_compiler)
    assert result["skipped"] == 1
    assert result["success"] == 0


def test_import_folder_failure(sources_dir, importer, mocker):
    """ingest 抛异常时标记为 failed"""
    (sources_dir / "data").mkdir()
    (sources_dir / "data" / "a.md").write_text("# A")

    mock_compiler = mocker.MagicMock()
    mock_compiler.ingest.side_effect = RuntimeError("boom")

    result = importer.import_folder("data", compiler=mock_compiler)
    assert result["failed"] == 1
    assert len(result["errors"]) == 1


# ============================================================================
# import_folder_async
# ============================================================================


def test_import_folder_async_enqueues(sources_dir, importer, mocker):
    """异步导入将文件加入队列"""
    (sources_dir / "papers").mkdir()
    (sources_dir / "papers" / "a.md").write_text("# A")
    (sources_dir / "papers" / "b.md").write_text("# B")

    mock_queue = mocker.MagicMock()
    mock_queue.enqueue.return_value = "job_xxx"

    result = importer.import_folder_async("papers", mock_queue)

    assert result["total"] == 2
    assert result["enqueued"] == 2
    assert mock_queue.enqueue.call_count == 2


def test_scan_folder_root_no_dot_prefix(sources_dir, importer):
    """扫描根目录（"."）时返回路径不应带 ./ 前缀（修复 2026-08-01）"""
    (sources_dir / "a.md").write_text("# A", encoding="utf-8")
    (sources_dir / "sub").mkdir()
    (sources_dir / "sub" / "b.md").write_text("# B", encoding="utf-8")

    files = importer._scan_folder(".")

    assert "a.md" in files
    assert "sub/b.md" in files
    assert not any(f.startswith("./") for f in files), f"不应有 ./ 前缀: {files}"
    assert not any("/." in f for f in files), f"不应有 /. 路径段: {files}"


def test_import_folder_async_only_changed(sources_dir, importer, mocker):
    """only_changed=True 时只入队缓存未命中的文件（新文件/已变化文件）"""
    from src.core.cache import IngestCache

    (sources_dir / "a.md").write_text("# A", encoding="utf-8")  # 新文件 → 入队
    (sources_dir / "b.md").write_text("# B", encoding="utf-8")

    # 先模拟 b.md 已处理过（写入缓存）
    cache = IngestCache(db_path=str(sources_dir.parent.parent / "test_cache.db"),
                        sources_dir=str(sources_dir))
    cache.mark_ingested("b.md")

    mock_queue = mocker.MagicMock()
    mock_queue.enqueue.return_value = "job_x"

    result = importer.import_folder_async(".", mock_queue, recurse=True, only_changed=True, cache=cache)

    assert result["total"] == 1, f"应只统计新文件: {result}"
    assert result["enqueued"] == 1
    enqueued_paths = [c.args[0] for c in mock_queue.enqueue.call_args_list]
    assert "a.md" in enqueued_paths
    assert "b.md" not in enqueued_paths


def test_import_folder_async_no_cache_param_keeps_behavior(sources_dir, importer, mocker):
    """不带 only_changed/cache 参数时行为不变（全量入队）"""
    (sources_dir / "a.md").write_text("# A", encoding="utf-8")
    (sources_dir / "b.md").write_text("# B", encoding="utf-8")

    mock_queue = mocker.MagicMock()
    result = importer.import_folder_async(".", mock_queue)

    assert result["enqueued"] == 2
