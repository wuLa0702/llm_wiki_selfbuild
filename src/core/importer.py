"""
文件夹导入器 — Phase 4 Step 8

递归扫描 raw/sources/ 下的文件，批量导入到知识库。
文件夹名作为 LLM 上下文注入，引导提取方向。
"""
import os

from src.core.logging_config import get_logger

logger = get_logger("importer")

# 支持的源文件扩展名
SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf", ".html", ".csv"}


class FolderImporter:
    """文件夹导入 — 扫描 + 队列 + 上下文注入"""

    def __init__(self, sources_dir: str = "raw/sources") -> None:
        """
        Args:
            sources_dir: 源文件根目录
        """
        self.sources_dir = sources_dir

    # ------------------------------------------------------------------
    # 同步导入
    # ------------------------------------------------------------------

    def import_folder(
        self,
        folder_path: str,
        recurse: bool = True,
        compiler=None,
    ) -> dict:
        """
        同步导入文件夹 — 逐个文件调用 WikiCompiler.ingest()

        Args:
            folder_path: 文件夹路径（相对于 raw/sources/）
            recurse: 是否递归子目录
            compiler: WikiCompiler 实例。不传则内部创建。

        Returns:
            {
                "total": 12,
                "success": 10,
                "skipped": 2,
                "failed": 0,
                "pages_created": 15,
                "pages_updated": 3,
                "errors": [],
                "folder_name": "llm-papers",
            }
        """
        files = self._scan_folder(folder_path, recurse)
        if not files:
            logger.info("文件夹为空或不存在 | path=%s", folder_path)
            return {"total": 0, "success": 0, "skipped": 0, "failed": 0, "pages_created": 0, "pages_updated": 0, "errors": []}

        # 提取文件夹名作为上下文
        folder_name = os.path.basename(folder_path.rstrip("/\\"))
        folder_context = f"该文件位于「{folder_name}」目录下，请关注与此主题相关的实体和概念。"

        if compiler is None:
            from src.core.wiki_compiler import WikiCompiler
            compiler = WikiCompiler()

        total = len(files)
        success = 0
        skipped = 0
        failed = 0
        pages_created = 0
        pages_updated = 0
        errors: list[dict] = []

        for source_path in files:
            try:
                result = compiler.ingest(source_path, folder_context=folder_context)
                status = result.get("status", "")
                if status == "success":
                    success += 1
                    pages_created += len(result.get("pages_created", []))
                    pages_updated += len(result.get("pages_updated", []))
                elif status == "skipped":
                    skipped += 1
                else:
                    failed += 1
                    errors.append({"file": source_path, "error": f"未知状态: {status}"})
            except Exception as exc:
                failed += 1
                errors.append({"file": source_path, "error": str(exc)})
                logger.error("文件夹导入失败 | file=%s error=%s", source_path, exc)

        logger.info(
            "文件夹导入完成 | folder=%s total=%d success=%d skipped=%d failed=%d created=%d",
            folder_name, total, success, skipped, failed, pages_created,
        )

        return {
            "total": total,
            "success": success,
            "skipped": skipped,
            "failed": failed,
            "pages_created": pages_created,
            "pages_updated": pages_updated,
            "errors": errors,
            "folder_name": folder_name,
        }

    # ------------------------------------------------------------------
    # 队列导入（异步）
    # ------------------------------------------------------------------

    def import_folder_async(
        self,
        folder_path: str,
        ingest_queue,
        recurse: bool = True,
    ) -> dict:
        """
        异步导入文件夹 — 文件加入 IngestQueue 逐个处理

        Args:
            folder_path: 文件夹路径（相对于 raw/sources/）
            ingest_queue: IngestQueue 实例
            recurse: 是否递归子目录

        Returns:
            {"total": 12, "enqueued": 12, "queue_id": "xxx"}
        """
        files = self._scan_folder(folder_path, recurse)
        if not files:
            return {"total": 0, "enqueued": 0}

        folder_name = os.path.basename(folder_path.rstrip("/\\"))
        context = {"folder": folder_name}

        enqueued = 0
        job_ids: list[str] = []
        for source_path in files:
            job_id = ingest_queue.enqueue(source_path, context=context)
            job_ids.append(job_id)
            enqueued += 1

        logger.info("文件夹异步导入 | folder=%s total=%d enqueued=%d", folder_name, len(files), enqueued)
        return {
            "total": len(files),
            "enqueued": enqueued,
            "job_ids": job_ids,
            "folder_name": folder_name,
        }

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _scan_folder(self, folder_path: str, recurse: bool = True) -> list[str]:
        """
        扫描文件夹，返回支持的源文件相对路径列表

        Args:
            folder_path: 文件夹路径（相对于 raw/sources/）
            recurse: 是否递归子目录

        Returns:
            相对路径列表，如 ["llm-papers/transformer.md", ...]
        """
        full_path = os.path.join(self.sources_dir, folder_path)
        if not os.path.isdir(full_path):
            logger.warning("文件夹不存在 | path=%s", full_path)
            return []

        files: list[str] = []
        base_len = len(self.sources_dir) + 1  # "raw/sources/" 的长度

        for root, dirs, fnames in os.walk(full_path):
            if not recurse:
                # 不递归时只处理当前目录层级
                dirs.clear()

            for fname in fnames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    continue
                if fname.startswith("."):
                    continue

                full_file = os.path.join(root, fname)
                rel = full_file[base_len:].replace("\\", "/")
                files.append(rel)

        return sorted(files)
