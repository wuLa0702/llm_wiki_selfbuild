"""
Wiki 页面健康检查器 — Phase 3 静态检测 + Phase 4 LLM 语义检测

- 静态检测：断链、孤页、index 缺口（零 LLM 成本）
- 语义检测：矛盾、知识缺口、浅页面（1 次 LLM 调用 + SQLite 持久化缓存）
"""
import json
import os
import random

from src.core.graph import WikiGraph
from src.core.logging_config import get_logger
from src.llm.adapter import LLMAdapter
from src.llm.prompts import SYSTEM_PROMPT_LINT_SEMANTIC

logger = get_logger("linter")

# 导航文件 — 孤页检测中跳过
NAV_FILES = {"index.md", "overview.md", "log.md"}

# 语义检测 — 页面采样上限（超过此数量按社区抽样）
MAX_SEMANTIC_PAGES = 500

# 脏标记：ingest 后设为 True，下次语义 lint 自动重新调用 LLM
_LINT_CACHE_DIRTY = False


class LintTool:
    """Wiki 页面健康检查器 — 静态 + 语义检测"""

    def __init__(self, wiki_dir: str = "wiki") -> None:
        """
        Args:
            wiki_dir: wiki 目录路径
        """
        self.wiki_dir = wiki_dir
        self._graph: WikiGraph | None = None

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    @property
    def graph(self) -> WikiGraph:
        """懒加载 WikiGraph 实例"""
        if self._graph is None:
            self._graph = WikiGraph(wiki_dir=self.wiki_dir)
            self._graph.build()
        return self._graph

    @staticmethod
    def _is_http_link(target: str) -> bool:
        """判断是否为 HTTP/HTTPS 外部链接"""
        return target.startswith("http://") or target.startswith("https://")

    @staticmethod
    def _read_file(path: str) -> str | None:
        """安全读取文件内容，失败返回 None"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeDecodeError) as exc:
            logger.debug("无法读取文件 | path=%s error=%s", path, exc)
            return None

    # ------------------------------------------------------------------
    # 检测1：断链
    # ------------------------------------------------------------------

    def check_broken_links(self) -> list[dict]:
        """
        检测断链：[[target]] 指向不存在的文件

        跳过 HTTP/HTTPS 外部链接。

        Returns:
            [{"source_page": "entities/xxx.md", "broken_target": "entities/nonexistent.md"}]
        """
        g = self.graph
        existing_nodes = set(g.nodes())
        broken: list[dict] = []

        for source, target in g.edges():
            if self._is_http_link(target):
                continue
            # 目标存在于 nodes() 中 → 有效链接
            if target in existing_nodes:
                continue
            broken.append({
                "source_page": source,
                "broken_target": target,
            })

        logger.info("断链检测完成 | count=%d", len(broken))
        return broken

    # ------------------------------------------------------------------
    # 检测2：孤页
    # ------------------------------------------------------------------

    def check_orphan_pages(self) -> list[str]:
        """
        检测孤页：没有任何页面链接到它（0 入链）

        排除 index.md, overview.md, log.md 等导航页面。

        Returns:
            孤页路径列表 ["concepts/forgotten.md", ...]
        """
        g = self.graph
        orphans: list[str] = []

        for node in g.nodes():
            if node in NAV_FILES:
                continue
            deg = g.degree(node)
            if deg["in_degree"] == 0:
                orphans.append(node)

        logger.info("孤页检测完成 | count=%d", len(orphans))
        return orphans

    # ------------------------------------------------------------------
    # 检测3：index 缺失
    # ------------------------------------------------------------------

    def check_index_gaps(self) -> list[str]:
        """
        检测 index.md 中缺失的页面：wiki/ 下存在但 index.md 未列出的页面

        通过扫描 index.md 内容，收集其中出现的所有 wikilinks 路径，
        与全部页面路径对比，找出未在 index 中引用的页面。
        排除 index.md、overview.md、log.md 自身。

        Returns:
            缺失页面路径列表 ["entities/new_page.md", ...]
        """
        index_path = os.path.join(self.wiki_dir, "index.md")
        index_text = self._read_file(index_path)
        if index_text is None:
            logger.info("index.md 不存在，跳过 index 缺口检测")
            return []

        # 收集 index.md 中引用的所有页面路径
        from src.core.graph import WIKILINK_PATTERN as PATTERN

        referenced: set[str] = set()
        for m in PATTERN.finditer(index_text):
            target = m.group(1).strip()
            if not self._is_http_link(target):
                referenced.add(target)

        # 对比所有页面
        g = self.graph
        gaps: list[str] = []
        for node in g.nodes():
            if node in NAV_FILES:
                continue
            if node not in referenced:
                gaps.append(node)

        logger.info("Index 缺口检测完成 | count=%d", len(gaps))
        return sorted(gaps)

    # ------------------------------------------------------------------
    # 汇总
    # ------------------------------------------------------------------

    def run_all(self) -> dict:
        """
        运行全部静态检查

        Returns:
            {
                "broken_links": [...],
                "broken_links_count": 3,
                "orphan_pages": [...],
                "orphan_pages_count": 1,
                "index_gaps": [...],
                "index_gaps_count": 2,
                "health_score": 85,
                "summary": "检测摘要文本"
            }
        """
        broken = self.check_broken_links()
        orphans = self.check_orphan_pages()
        gaps = self.check_index_gaps()

        # 健康评分：100 起，逐项扣分
        score = 100
        score -= len(broken) * 5
        score -= len(orphans) * 10
        score -= len(gaps) * 3
        score = max(0, score)

        # 构建摘要
        parts: list[str] = []
        if broken:
            parts.append(f"断链 {len(broken)} 处")
        if orphans:
            parts.append(f"孤页 {len(orphans)} 个")
        if gaps:
            parts.append(f"index 缺口 {len(gaps)} 个")
        summary = "健康" if score == 100 else f"需关注（{'，'.join(parts)}）" if parts else "健康"

        result = {
            "broken_links": broken,
            "broken_links_count": len(broken),
            "orphan_pages": orphans,
            "orphan_pages_count": len(orphans),
            "index_gaps": gaps,
            "index_gaps_count": len(gaps),
            "health_score": score,
            "summary": f"Wiki 健康评分 {score}/100 · {summary}",
        }

        logger.info("Lint 全部检测完成 | score=%d broken=%d orphans=%d gaps=%d",
                     score, len(broken), len(orphans), len(gaps))
        return result

    # ------------------------------------------------------------------
    # Phase 4 Step 5 — LLM 语义检测
    # ------------------------------------------------------------------

    def check_semantic(self, llm: LLMAdapter, repo) -> dict:
        """
        调用 1 次 LLM 做语义检测（矛盾 + 知识缺口 + 浅页面）

        缓存策略：
          - SQLite 持久化缓存（跨进程/重启可用）
          - ingest 后通过 mark_lint_cache_dirty() 置脏，下次自动刷新
          - 无时间 TTL，只依赖脏标记

        Args:
            llm: LLMAdapter 实例
            repo: WikiRepository 实例

        Returns:
            {
                "contradictions": [...],
                "knowledge_gaps": [...],
                "shallow_pages": [...],
                "cached": false,
                "summary": "语义检测摘要",
            }
        """
        global _LINT_CACHE_DIRTY

        # 脏标记检查：不脏且有 SQLite 缓存 → 返回缓存
        if not _LINT_CACHE_DIRTY:
            cached = repo.get_lint_cache()
            if cached:
                logger.info("语义 Lint SQLite 缓存命中")
                cached["cached"] = True
                return cached

        # 收集页面摘要（含采样）
        pages_summary, sampled_total, total_pages = self._collect_pages_summary(repo)
        if not pages_summary:
            logger.info("语义 Lint 跳过：无页面数据")
            return {
                "contradictions": [],
                "knowledge_gaps": [],
                "shallow_pages": [],
                "cached": False,
                "summary": "Wiki 中没有页面可检测",
            }

        # 构建 prompt（标注采样信息）
        prompt = "请分析以下 Wiki 页面的语义问题（矛盾、知识缺口、浅页面）。\n\n"
        if sampled_total < total_pages:
            prompt += f"（共 {total_pages} 页，按社区抽样展示 {sampled_total} 页）\n\n"
        prompt += "页面列表：\n" + pages_summary

        # 输出 schema
        schema = {
            "type": "object",
            "properties": {
                "contradictions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "page_a": {"type": "string"},
                            "page_b": {"type": "string"},
                            "claim_a": {"type": "string"},
                            "claim_b": {"type": "string"},
                            "description": {"type": "string"},
                            "confidence": {"type": "string", "enum": ["high", "low"]},
                        },
                        "required": ["page_a", "page_b", "description", "confidence"],
                    },
                },
                "knowledge_gaps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "mentioned_in": {"type": "array", "items": {"type": "string"}},
                            "description": {"type": "string"},
                        },
                        "required": ["topic", "description"],
                    },
                },
                "shallow_pages": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "page": {"type": "string"},
                            "reason": {"type": "string"},
                            "suggestion": {"type": "string"},
                        },
                        "required": ["page", "reason"],
                    },
                },
            },
            "required": ["contradictions", "knowledge_gaps", "shallow_pages"],
        }

        try:
            result = llm.chat_structured(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT_LINT_SEMANTIC,
                output_schema=schema,
                operation="lint_semantic",
            )

            result.setdefault("contradictions", [])
            result.setdefault("knowledge_gaps", [])
            result.setdefault("shallow_pages", [])

            total = (
                len(result["contradictions"])
                + len(result["knowledge_gaps"])
                + len(result["shallow_pages"])
            )

            # 写入 SQLite 缓存 + 清除脏标记
            cache_entry = {
                "contradictions": result.get("contradictions", []),
                "knowledge_gaps": result.get("knowledge_gaps", []),
                "shallow_pages": result.get("shallow_pages", []),
                "summary": f"语义检测完成，发现 {total} 个问题",
            }
            repo.save_lint_cache(cache_entry)
            _LINT_CACHE_DIRTY = False

            logger.info("语义 Lint 完成 | contradictions=%d gaps=%d shallow=%d",
                         len(result["contradictions"]),
                         len(result["knowledge_gaps"]),
                         len(result["shallow_pages"]))

            return {
                "contradictions": result.get("contradictions", []),
                "knowledge_gaps": result.get("knowledge_gaps", []),
                "shallow_pages": result.get("shallow_pages", []),
                "cached": False,
                "summary": f"语义检测完成，发现 {total} 个问题",
            }

        except Exception as exc:
            logger.error("语义 Lint LLM 调用失败 | %s", exc)
            return {
                "contradictions": [],
                "knowledge_gaps": [],
                "shallow_pages": [],
                "cached": False,
                "summary": f"语义检测失败：{exc}",
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # 语义检测 — 辅助方法
    # ------------------------------------------------------------------

    def _collect_pages_summary(self, repo) -> tuple[str, int, int]:
        """
        收集页面摘要，超过 MAX_SEMANTIC_PAGES 时按社区抽样

        Args:
            repo: WikiRepository 实例

        Returns:
            (summary_text, sampled_count, total_count)
        """
        all_nodes = [
            p for p in self.graph.nodes()
            if p not in NAV_FILES
        ]
        total_pages = len(all_nodes)
        if total_pages == 0:
            return ("", 0, 0)

        # 如果未超过上限，全部返回
        if total_pages <= MAX_SEMANTIC_PAGES:
            sampled_nodes = all_nodes
        else:
            # 按社区分层抽样
            sampled_nodes = self._sample_pages(all_nodes, total_pages)
            logger.info("语义 Lint 页面抽样 | total=%d sampled=%d", total_pages, len(sampled_nodes))

        lines: list[str] = []
        for page_path in sampled_nodes:
            meta = repo.get_page(page_path)
            if not meta:
                continue

            title = meta.get("title", page_path)
            page_type = meta.get("page_type", "unknown")
            word_count = meta.get("word_count", 0)

            full_path = os.path.join(self.wiki_dir, page_path)
            try:
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read(500)
                if content.startswith("---"):
                    end = content.find("---", 3)
                    if end > 0:
                        content = content[end + 3:].strip()
                summary = content[:200].replace("\n", " ")
            except (OSError, UnicodeDecodeError):
                summary = "(无法读取)"

            lines.append(
                f"---\n路径: {page_path}\n"
                f"标题: {title}\n"
                f"类型: {page_type}\n"
                f"字数: {word_count}\n"
                f"摘要: {summary}\n"
            )

        if not lines:
            return ("", 0, total_pages)

        return ("\n".join(lines), len(sampled_nodes), total_pages)

    def _sample_pages(self, all_nodes: list[str], total: int) -> list[str]:
        """
        按社区分层抽样

        优先使用 Louvain 社区做分层，无社区则均匀采样。

        Args:
            all_nodes: 所有页面路径
            total: 页面总数

        Returns:
            抽样后的页面列表（约 MAX_SEMANTIC_PAGES 个）
        """
        # 尝试按社区分组
        try:
            comm_result = self.graph.communities()
            communities = comm_result.get("communities", {})
        except Exception:
            communities = {}

        if communities and len(communities) > 1:
            # 社区成员映射
            comm_members: dict[str, list[str]] = {}
            for cid_str, cdata in communities.items():
                members = [m for m in cdata.get("members", []) if m in all_nodes]
                if members:
                    comm_members[cid_str] = members

            # 按社区大小比例分配配额
            sampled: list[str] = []
            quota = MAX_SEMANTIC_PAGES // len(comm_members)
            for cid_str, members in comm_members.items():
                if len(members) <= quota:
                    sampled.extend(members)
                else:
                    # 随机均匀选取 quota 个
                    random.shuffle(members)
                    sampled.extend(members[:quota])

            # 如果未满 MAX_SEMANTIC_PAGES，补充
            remaining = MAX_SEMANTIC_PAGES - len(sampled)
            if remaining > 0:
                existing = set(sampled)
                extra = [n for n in all_nodes if n not in existing]
                random.shuffle(extra)
                sampled.extend(extra[:remaining])

            return sampled
        else:
            # 无社区：均匀采样，取前 MAX_SEMANTIC_PAGES 个
            random.shuffle(all_nodes)
            return all_nodes[:MAX_SEMANTIC_PAGES]


# ====================================================================
# 模块级函数：脏标记管理（供 WikiCompiler 在 ingest 后调用）
# ====================================================================


def mark_lint_cache_dirty() -> None:
    """标记语义 Lint 缓存为脏

    在 ingest/delete 后调用，使下次 check_semantic() 跳过缓存重新检测。
    """
    global _LINT_CACHE_DIRTY
    _LINT_CACHE_DIRTY = True
    logger.debug("语义 Lint 缓存已置脏")


def auto_fix_wikilinks(wiki_dir: str = "wiki") -> dict:
    """导入后自动修复裸名 wikilink → 完整路径。"""
    import re, os
    name_to_path = {}
    for root, dirs, fnames in os.walk(wiki_dir):
        for f in fnames:
            if not f.endswith('.md'): continue
            full = os.path.relpath(os.path.join(root, f), wiki_dir).replace("\\", "/")
            bare = f.replace('.md', '')
            name_to_path[bare] = full
            name_to_path[full.replace('.md', '')] = full
    fixed = 0; unfixable = 0
    pat = re.compile(r'\[\[([^\]|]+?)(?:\|([^\]]+?))?\]\]')
    for root, dirs, fnames in os.walk(wiki_dir):
        for f in fnames:
            if not f.endswith('.md'): continue
            fp = os.path.join(root, f)
            content = open(fp, 'r', encoding='utf-8').read()
            modified = False
            def repl(m):
                nonlocal modified
                t = m.group(1).strip()
                d = m.group(2)
                if '/' in t:
                    if not t.endswith('.md'):
                        full = name_to_path.get(t)
                        if full: modified = True; return f'[[{full}|{d or t}]]'
                    return m.group(0)
                full = name_to_path.get(t)
                if full: modified = True; return f'[[{full}|{d or t}]]'
                return m.group(0)
            new_c = pat.sub(repl, content)
            if modified:
                open(fp, 'w', encoding='utf-8').write(new_c); fixed += 1
    for root, dirs, fnames in os.walk(wiki_dir):
        for f in fnames:
            if not f.endswith('.md'): continue
            for m in pat.finditer(open(os.path.join(root,f),'r',encoding='utf-8').read()):
                t = m.group(1).strip()
                if '/' not in t and t not in name_to_path: unfixable += 1
    return {"fixed": fixed, "unfixable": unfixable}


def suggest_correction(broken_target: str, existing_nodes: set[str], threshold: float = 0.6) -> str | None:
    """模糊匹配断链目标到已有页面。"""
    import difflib
    best, best_score = None, threshold
    for node in existing_nodes:
        bare_node = node.split('/')[-1].replace('.md','')
        bare_target = broken_target.split('/')[-1].replace('.md','')
        score = difflib.SequenceMatcher(None, bare_target.lower(), bare_node.lower()).ratio()
        if score > best_score: best_score, best = score, node
    return best


def create_stub(target: str, wiki_dir: str = "wiki") -> str | None:
    """为断链创建存根页面。"""
    import datetime, os
    fp = os.path.join(wiki_dir, target)
    if os.path.exists(fp): return None
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    name = target.split('/')[-1].replace('.md','')
    stub = f"---\ntitle: '{name}'\ntype: query\ncreated: {datetime.date.today().isoformat()}\ntags: [待补充]\n---\n\n# {name}\n\n> 此页面由健康检查自动创建，等待后续导入时填充内容。\n"
    open(fp, 'w', encoding='utf-8').write(stub)
    return target


def fill_missing_links(wiki_dir: str = "wiki") -> int:
    """为入链=0的页面补充反向引用。"""
    import re, os
    NAV_FILES = {'index.md','overview.md','log.md','wiki-schema.md'}
    all_pages = []
    page_links = {}
    for root, dirs, fnames in os.walk(wiki_dir):
        for f in fnames:
            if f.endswith('.md'):
                path = os.path.relpath(os.path.join(root,f),wiki_dir).replace("\\","/")
                content = open(os.path.join(root,f),'r',encoding='utf-8').read()
                page_links[path] = set(re.findall(r'\[\[([^\]|]+?)(?:\|[^\]]+?)?\]\]', content))
                all_pages.append(path)
    inbound = {p: set() for p in all_pages}
    for src, targets in page_links.items():
        for t in targets:
            for p in all_pages:
                if p == t or p.endswith('/'+t.replace('.md','')) or t == p.split('/')[-1].replace('.md',''):
                    inbound[p].add(src)
    orphans = [p for p in all_pages if len(inbound[p])==0 and p not in NAV_FILES]
    modified = 0
    for orphan in orphans[:10]:
        prefix = orphan.split('/')[0]+'/' if '/' in orphan else ''
        candidates = [p for p in all_pages if p!=orphan and p.startswith(prefix)] or [p for p in all_pages if p!=orphan and p not in NAV_FILES]
        if not candidates: continue
        best = max(candidates, key=lambda p: len(page_links.get(p,set())))
        with open(os.path.join(wiki_dir,best),'a',encoding='utf-8') as fh:
            fh.write(f'\n\n[[{orphan}]]')
        modified += 1
    return modified
