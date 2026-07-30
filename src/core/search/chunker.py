"""
Chunk 切分引擎 — Markdown heading-based 篇章分割

按 ## / ### / #### 标题层级切分，约束大小，保留面包屑上下文。
只做纯文本切分，不涉及向量化或持久化。

设计原则：
  - heading-based（利用 Wiki 页面已有的标题结构）
  - 不做 sliding window（过度工程，增加 3-5 倍索引量）
  - 不做 semantic chunking（需 LLM 调用，Wiki 页面标题已提供足够结构）
"""

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("search.chunker")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

# 切分参数（字符级别）
CHUNK_TARGET_SIZE = 600       # 目标大小
CHUNK_MAX_SIZE = 1200         # 超过此值强制二次切分
CHUNK_MIN_SIZE = 100          # 小于此值合并到前一个 chunk
CHUNK_OVERLAP = 100           # 相邻 chunk 重叠字符数

# 需要多大才算"长段落"（超过此值按段落切分）
PARAGRAPH_SPLIT_MIN = 800

# 标题匹配：## 到 ####
HEADING_RE = re.compile(r"^(#{2,4})\s+(.+)$", re.MULTILINE)

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------


@dataclass
class Chunk:
    """单个 Chunk

    Attributes:
        id: 内容 hash（sha256[:12]），稳定可去重
        path: Wiki 页面路径，如 entities/python.md
        content: 送入 embedding 的文本（含面包屑前缀）
        heading: 本级标题
        level: 标题级别（2=##, 3=###, 4=####）
        breadcrumb: 父标题链，如 ["Python", "数据类型"]
        start_line: 在原始页面的起始行号（1-based）
        end_line: 在原始页面的结束行号（含）
        chunk_index: 该页面中的第几个 chunk（0-based）
        total_chunks: 该页面总 chunk 数
        page_hash: 页面内容的完整 hash（用于增量检测）
    """
    id: str
    path: str
    content: str
    heading: str
    level: int
    breadcrumb: list[str] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    chunk_index: int = 0
    total_chunks: int = 1
    page_hash: str = ""

    def to_metadata(self) -> dict:
        """转为 Chroma metadata dict"""
        return {
            "path": self.path,
            "heading": self.heading,
            "level": self.level,
            "breadcrumb": " > ".join(self.breadcrumb) if self.breadcrumb else "",
            "start_line": self.start_line,
            "end_line": self.end_line,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "page_hash": self.page_hash,
        }


@dataclass
class Section:
    """解析出的原始章节"""
    heading: str
    level: int
    breadcrumb: list[str]
    start_line: int
    lines: list[str]


# ---------------------------------------------------------------------------
# 核心 API
# ---------------------------------------------------------------------------


def chunk_page(path: str, content: str, **kwargs) -> list[Chunk]:
    """将一个 Wiki 页面切分为 Chunk 列表

    Args:
        path: 页面路径，如 entities/python.md
        content: 页面 Markdown 完整内容
        **kwargs: 可覆盖 CHUNK_TARGET_SIZE / CHUNK_MAX_SIZE 等常量

    Returns:
        Chunk 列表。至少返回一个 chunk（页面无标题时全部作为单个 chunk）。
    """
    target = kwargs.get("target_size", CHUNK_TARGET_SIZE)
    max_size = kwargs.get("max_size", CHUNK_MAX_SIZE)
    min_size = kwargs.get("min_size", CHUNK_MIN_SIZE)
    overlap = kwargs.get("overlap", CHUNK_OVERLAP)
    page_hash = _page_hash(content)

    # Step 1: 解析标题树 → 原始 Section 列表
    sections = _parse_headings(content)

    # Step 2: 将 Section 转为初始 Chunk（可能过大或过小）
    raw_chunks = _sections_to_chunks(sections, path, page_hash)

    # Step 3: 大小约束 — 合并过小 / 切分过大
    adjusted = _adjust_chunks(raw_chunks, path, page_hash, target, max_size, min_size, overlap)

    # Step 4: 编号
    for i, c in enumerate(adjusted):
        c.chunk_index = i
        c.total_chunks = len(adjusted)

    logger.debug("chunk_page | path=%s chunks=%d", path, len(adjusted))
    return adjusted


# ---------------------------------------------------------------------------
# Step 1: 标题树解析
# ---------------------------------------------------------------------------


def _parse_headings(content: str) -> list[Section]:
    """解析 Markdown 标题树，返回 Section 列表

    按 ## 切分主章节，内部保留 ### / #### 层级。
    无标题部分作为顶部 section（heading=""）。
    """
    lines = content.split("\n")
    sections: list[Section] = []

    # 标题栈，用于 breadcrumb
    heading_stack: list[tuple[str, int]] = []  # [(heading, level), ...]

    current_lines: list[str] = []
    current_line_num = 1

    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            # 保存当前 section
            section = _flush_current(current_lines, heading_stack, current_line_num)
            if section:
                sections.append(section)

            level = len(m.group(1))  # # 数量
            heading_text = m.group(2).strip()

            # 更新标题栈
            _update_heading_stack(heading_stack, heading_text, level)

            current_lines = []
            current_line_num = i + 1
        else:
            current_lines.append(line)

    # 最后一个 section
    section = _flush_current(current_lines, heading_stack, current_line_num)
    if section:
        sections.append(section)

    # 如果没有解析出任何 section（无标题），整页作为一个 section
    if not sections:
        sections.append(Section(
            heading="",
            level=0,
            breadcrumb=[],
            start_line=1,
            lines=lines,
        ))

    return sections


def _flush_current(
    lines: list[str],
    heading_stack: list[tuple[str, int]],
    start_line: int,
) -> Optional[Section]:
    """将当前累积的行 flush 为一个 Section"""
    # 过滤掉纯空内容
    text = "\n".join(lines).strip()
    if not text and not heading_stack:
        return None

    # 从 heading_stack 取当前标题
    if heading_stack:
        current_heading, current_level = heading_stack[-1]
        breadcrumb = [h for h, _ in heading_stack[:-1]]
    else:
        current_heading = ""
        current_level = 0
        breadcrumb = []

    return Section(
        heading=current_heading,
        level=current_level,
        breadcrumb=breadcrumb,
        start_line=start_line,
        lines=list(lines),  # copy
    )


def _update_heading_stack(
    stack: list[tuple[str, int]],
    heading: str,
    level: int,
) -> None:
    """维护标题栈：同层替换，深层入栈，浅层弹出"""
    while stack and stack[-1][1] >= level:
        stack.pop()
    stack.append((heading, level))


# ---------------------------------------------------------------------------
# Step 2: Section → 初始 Chunk
# ---------------------------------------------------------------------------


def _sections_to_chunks(
    sections: list[Section],
    path: str,
    page_hash: str,
) -> list[Chunk]:
    """将 Section 列表转为初始 Chunk（尚未做大小约束）"""
    chunks: list[Chunk] = []

    for sec in sections:
        content_text = "\n".join(sec.lines).strip()
        if not content_text:
            continue

        # 面包屑前缀
        prefix = ""
        if sec.breadcrumb:
            prefix = " > ".join(sec.breadcrumb) + " > "
        if sec.heading:
            prefix += sec.heading + "\n\n"
        elif prefix:
            prefix += "\n\n"

        full_content = prefix + content_text

        # 计算行号范围
        end_line = sec.start_line + len(sec.lines) - 1

        chunk_id = _make_chunk_id(full_content)

        chunks.append(Chunk(
            id=chunk_id,
            path=path,
            content=full_content,
            heading=sec.heading,
            level=sec.level,
            breadcrumb=sec.breadcrumb,
            start_line=sec.start_line,
            end_line=end_line,
            page_hash=page_hash,
        ))

    return chunks


# ---------------------------------------------------------------------------
# Step 3: 大小约束调整
# ---------------------------------------------------------------------------


def _adjust_chunks(
    chunks: list[Chunk],
    path: str,
    page_hash: str,
    target: int,
    max_size: int,
    min_size: int,
    overlap: int,
) -> list[Chunk]:
    """调整 chunk 大小：合并过小，切分过大

    合并规则：
      - 过小 chunk（≤ min_size）优先向前合并到 buffer
      - 仅合并有相同 breadcrumb 的 chunk（同父层级），防止跨层级合并
      - 跨层级且过小的 chunk 保持独立（宁碎不乱）
    """
    if not chunks:
        return chunks

    adjusted: list[Chunk] = []
    buffer: Optional[Chunk] = None

    for chunk in chunks:
        size = len(chunk.content)
        same_parent = (
            buffer is not None
            and chunk.breadcrumb == buffer.breadcrumb
        )

        if size <= min_size and same_parent:
            # 过小且同父 → 合并到前一个 chunk
            buffer = _merge_chunks(buffer, chunk)  # type: ignore[arg-type]
        elif size > max_size:
            # 过大 → 切分
            if buffer is not None:
                adjusted.append(buffer)
                buffer = None
            split_chunks = _split_oversized(chunk, path, page_hash, target, overlap)
            adjusted.extend(split_chunks)
        else:
            # 大小合适
            if buffer is not None:
                adjusted.append(buffer)
            buffer = chunk

    if buffer is not None:
        adjusted.append(buffer)

    return adjusted


def _merge_chunks(a: Chunk, b: Chunk) -> Chunk:
    """合并两个相邻 chunk（调用方保证同 breadcrumb）"""
    merged_content = a.content + "\n" + b.content
    return Chunk(
        id=_make_chunk_id(merged_content),
        path=a.path,
        content=merged_content,
        heading=a.heading or b.heading,
        level=min(a.level, b.level) if a.level and b.level else (a.level or b.level),
        breadcrumb=list(a.breadcrumb) if a.breadcrumb else list(b.breadcrumb),
        start_line=min(a.start_line, b.start_line) if a.start_line and b.start_line else (a.start_line or b.start_line),
        end_line=max(a.end_line, b.end_line) if a.end_line and b.end_line else (a.end_line or b.end_line),
        page_hash=a.page_hash or b.page_hash,
    )


def _split_oversized(
    chunk: Chunk,
    path: str,
    page_hash: str,
    target: int,
    overlap: int,
) -> list[Chunk]:
    """将超大 chunk 按段落边界切分为多个 chunk"""
    text = chunk.content
    result: list[Chunk] = []

    # 尝试按段落（双换行）切分
    paragraphs = re.split(r"\n\n+", text)

    # 过滤 heading-only 段落（纯标题行，不含实质性内容）
    paragraphs = [p for p in paragraphs if len(p.strip()) > 20]
    if not paragraphs:
        return [chunk]

    if len(paragraphs) <= 1 or len(text) < PARAGRAPH_SPLIT_MIN:
        # 没有段落或内容不多 → 按字符位置硬切
        return _split_by_chars(chunk, path, page_hash, target, overlap)

    # 按段落合并到 target 大小
    current_paras: list[str] = []
    current_size = 0
    para_start_line = chunk.start_line

    for para in paragraphs:
        para_size = len(para) + 2  # +2 for \n\n

        if current_size + para_size > target * 1.2 and current_paras:
            # 当前批次已够大，flush
            content = "\n\n".join(current_paras)
            result.append(Chunk(
                id=_make_chunk_id(content),
                path=path,
                content=content,
                heading=chunk.heading,
                level=chunk.level,
                breadcrumb=chunk.breadcrumb,
                start_line=para_start_line,
                end_line=chunk.end_line,
                page_hash=page_hash,
            ))
            first_chunk = False

            # 添加 overlap：保留上一个 chunk 的最后几个段落
            overlap_text = _get_overlap_text(current_paras, overlap)
            if overlap_text:
                current_paras = [overlap_text]
                current_size = len(overlap_text)
                para_start_line = chunk.end_line
            else:
                current_paras = []
                current_size = 0
                para_start_line = chunk.end_line

        current_paras.append(para)
        current_size += para_size

    # 最后一个段落组
    if current_paras:
        content = "\n\n".join(current_paras)
        result.append(Chunk(
            id=_make_chunk_id(content),
            path=path,
            content=content,
            heading=chunk.heading,
            level=chunk.level,
            breadcrumb=chunk.breadcrumb,
            start_line=para_start_line,
            end_line=chunk.end_line,
            page_hash=page_hash,
        ))

    if not result:
        return _split_by_chars(chunk, path, page_hash, target, overlap)

    return result


def _split_by_chars(
    chunk: Chunk,
    path: str,
    page_hash: str,
    target: int,
    overlap: int,
) -> list[Chunk]:
    """按字符位置硬切（保底方案）"""
    text = chunk.content
    if len(text) <= target * 1.2:
        return [chunk]

    result: list[Chunk] = []
    start = 0
    chunk_idx = 0

    while start < len(text):
        end = min(start + target, len(text))

        # 尽量在句子/行边界切
        if end < len(text):
            # 在 end 附近找换行符
            newline_pos = text.rfind("\n", start, end + 50)
            if newline_pos > start + target // 2:
                end = newline_pos

        content = text[start:end].strip()
        if not content:
            break

        result.append(Chunk(
            id=_make_chunk_id(content),
            path=path,
            content=content,
            heading=chunk.heading,
            level=chunk.level,
            breadcrumb=chunk.breadcrumb,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            page_hash=page_hash,
        ))

        chunk_idx += 1
        # 下一次起点考虑 overlap
        start = end - overlap if end < len(text) else len(text)

    return result


def _get_overlap_text(paragraphs: list[str], overlap_chars: int) -> str:
    """从段落列表中提取末尾 overlap_chars 字符作为 overlap"""
    if not paragraphs:
        return ""
    collected: list[str] = []
    size = 0
    for p in reversed(paragraphs):
        p_size = len(p) + 2
        if size + p_size > overlap_chars and collected:
            break
        collected.insert(0, p)
        size += p_size
    return "\n\n".join(collected)


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _make_chunk_id(content: str) -> str:
    """基于内容生成 chunk ID"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


def _page_hash(content: str) -> str:
    """生成页面内容的 hash（用于增量检测）"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
