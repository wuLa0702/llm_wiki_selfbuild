import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FileText, Search, ChevronDown, ChevronRight, ArrowUpRight, Sparkles, Zap, Target } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Card } from '@/components/ui/card';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import EmptyState from '@/components/shared/EmptyState';

/** 单条命中位置（多命中时按章节切分） */
interface MatchPosition {
  section: string;
  snippet: string;
  line: number;
  score: number;
}

interface SearchResult {
  path: string;
  title?: string;
  snippet?: string;
  score?: number;        // 后端已归一化 [0, 1]
  raw_score?: number;    // 原始分（BM25 无界 / 向量余弦）
  metadata?: Record<string, unknown>;
  search_method?: string;
  rrf_score?: number;
  match_positions?: MatchPosition[];
}

type SearchMethod = 'bm25' | 'hybrid';

/** 置信度等级：high / medium / low（后端 score 已归一化 [0,1]） */
function confidenceLevel(score: number): 'high' | 'medium' | 'low' {
  if (score >= 0.65) return 'high';
  if (score >= 0.35) return 'medium';
  return 'low';
}

/** Pill 颜色：点 + 文字 */
const pillMeta = {
  high:   { dot: 'bg-emerald-500',  text: 'text-emerald-600 dark:text-emerald-400',  ring: 'ring-emerald-500/20' },
  medium: { dot: 'bg-blue-500',     text: 'text-blue-600 dark:text-blue-400',         ring: 'ring-blue-500/20' },
  low:    { dot: 'bg-slate-400',    text: 'text-slate-500 dark:text-slate-400',       ring: 'ring-slate-500/20' },
};

const methodMeta: Record<string, { label: string; icon: typeof Zap; desc: string }> = {
  bm25:   { label: 'BM25 关键词', icon: Zap,      desc: '基于关键词词频匹配，精确但不理解语义' },
  vector: { label: '向量语义',   icon: Sparkles,  desc: '基于语义相似度匹配，理解同义词但不精确' },
  hybrid: { label: '混合搜索',   icon: Target,    desc: '融合 BM25 + 向量语义，综合排序' },
};

/** 置信度 Pill：彩色圆点 + 百分比 */
function ScorePill({ score, rawScore, methodLabel }: { score: number; rawScore?: number; methodLabel?: string }) {
  const lvl = confidenceLevel(score);
  const m = pillMeta[lvl];
  const pct = Math.round(score * 100);
  return (
    <Tooltip>
      <TooltipTrigger render={<span className={`inline-flex items-center gap-1 text-[11px] font-medium tabular-nums ${m.text} ring-1 ${m.ring} rounded-full px-2 py-0.5 shrink-0`} />}>
        <span className={`w-1.5 h-1.5 rounded-full ${m.dot}`} />
        {pct}%
      </TooltipTrigger>
      <TooltipContent side="top" className="text-xs space-y-0.5">
        <div>归一化分 {score.toFixed(2)}</div>
        {methodLabel && <div className="text-[10px] text-muted-foreground">搜索方式：{methodLabel}</div>}
        {rawScore !== undefined && rawScore > 0 && (
          <div className="text-[10px] text-muted-foreground">原始分：{rawScore.toFixed(2)}</div>
        )}
      </TooltipContent>
    </Tooltip>
  );
}

/** 置信度说明薄带：搜索结果出现时常驻，不占额外空间 */
function LegendBar({ methodLabel }: { methodLabel: string }) {
  return (
    <div className="flex items-center gap-4 px-2 py-1.5 rounded-lg bg-muted/30 text-[11px] text-muted-foreground">
      <span className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />高 ≥0.65
      </span>
      <span className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />中 0.35–0.65
      </span>
      <span className="flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />低 &lt;0.35
      </span>
      <span className="ml-auto hidden sm:block">{methodLabel} · 分数归一化 [0,1]，越高越相关</span>
    </div>
  );
}

export default function SearchPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [actualMethod, setActualMethod] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [method, setMethod] = useState<SearchMethod>('bm25');
  /** 展开/收起多命中详情：key=index */
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  /** 翻页状态 */
  const PAGE_SIZE = 10;
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [totalMatched, setTotalMatched] = useState(0);
  const totalPages = Math.ceil(totalMatched / PAGE_SIZE);

  const effectiveMethod = actualMethod || method;
  const methodInfo = methodMeta[effectiveMethod] || methodMeta[method];

  const highlightSnippet = (text: string, keyword: string): React.ReactNode => {
    if (!keyword.trim() || !text) return text;
    const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const parts = text.split(new RegExp(`(${escaped})`, 'gi'));
    return parts.map((part, i) =>
      part.toLowerCase() === keyword.toLowerCase()
        ? <mark key={i} className="bg-yellow-200/70 dark:bg-yellow-500/30 text-inherit rounded-sm px-0.5 font-semibold">{part}</mark>
        : part
    );
  };

  const search = async (targetPage?: number) => {
    if (!query.trim()) return;
    const pg = targetPage ?? 0;
    setLoading(true);
    setExpanded({});
    if (pg === 0) setActualMethod('');
    try {
      const r = await fetch('/v1/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), k: PAGE_SIZE, offset: pg * PAGE_SIZE, method }),
      });
      const d = await r.json();
      // 过滤置信度低于 10% 的结果
      const filtered = (d.results || []).filter((res: SearchResult) => (res.score ?? 0) >= 0.1);
      setResults(filtered);
      setHasMore(d.has_more ?? false);
      setTotalMatched(d.total ?? filtered.length);
      setPage(pg);
      if (pg === 0) setActualMethod(d.method || method);
    } catch {}
    setLoading(false);
  };

  const toggleMethod = () => setMethod(method === 'hybrid' ? 'bm25' : 'hybrid');
  const toggleCard = (i: number) => setExpanded(prev => ({ ...prev, [i]: !prev[i] }));

  const goToPage = (path: string, line?: number) => {
    const params = new URLSearchParams({ path });
    const hash = line ? `#L${line}` : '';
    navigate(`/wiki?${params.toString()}${hash}`);
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Search bar area */}
      <div className="flex-shrink-0 border-b border-border bg-card">
        <div className="max-w-2xl mx-auto p-4 space-y-3">
          {/* Semantic search toggle */}
          <div className="flex items-center gap-3">
            <button
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-full border transition-all cursor-pointer ${
                method === 'hybrid'
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border text-muted-foreground hover:text-foreground hover:bg-accent'
              }`}
              onClick={toggleMethod}
            >
              <methodInfo.icon className={`h-3.5 w-3.5 ${method === 'hybrid' ? '' : 'opacity-50'}`} />
              {methodInfo.label}
            </button>
            <span className="text-[11px] text-muted-foreground/60">
              {methodInfo.desc}
            </span>
          </div>

          {/* Search input row */}
          <div className="flex gap-2">
            <Input
              placeholder="搜索知识库... (Enter 检索)"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && search()}
              className="flex-1"
            />
            <Button onClick={() => search()} disabled={loading || !query.trim()}>
              <Search className="h-4 w-4 mr-1" />
              {loading ? '搜索中...' : '搜索'}
            </Button>
          </div>

          {/* ──── 置信度说明薄带（常驻，有结果时显示） ──── */}
          {results.length > 0 && <LegendBar methodLabel={methodInfo.label} />}
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-2xl mx-auto">
          {loading ? (
            <div className="space-y-2">
              {[1,2,3,4].map(i => (
                <div key={i} className="p-3 rounded-lg border border-border">
                  <div className="flex items-center gap-2 mb-1.5">
                    <Skeleton className="h-3.5 w-3.5 rounded" />
                    <Skeleton className="h-4 w-48" />
                  </div>
                  <Skeleton className="h-3 w-32 mb-2" />
                  <Skeleton className="h-8 w-full" />
                </div>
              ))}
            </div>
          ) : results.length > 0 ? (
            <div className="space-y-2">
              {results.map((r, i) => {
                const score = r.score ?? 0;
                const title = r.title || r.path.split('/').pop() || r.path;
                const hasMulti = r.match_positions && r.match_positions.length > 0;
                const isOpen = expanded[i];
                const methodLabel = r.search_method ? methodMeta[r.search_method]?.label || r.search_method : '';

                return (
                  <Card
                    key={i}
                    className={`overflow-hidden transition-all duration-150 hover:shadow-md ${isOpen ? 'ring-1 ring-primary/20' : ''}`}
                  >
                    {/* ── 主卡片：文件级结果 ── */}
                    <div
                      className="p-3 cursor-pointer hover:bg-accent/30 transition-colors"
                      onClick={() => goToPage(r.path)}
                    >
                      {/* 顶栏：图标 + 标题 + 置信度 Pill（一行搞定） */}
                      <div className="flex items-center gap-2 mb-1">
                        <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        <span className="text-sm font-medium truncate flex-1 min-w-0">{title}</span>
                        <ScorePill score={score} rawScore={r.raw_score} methodLabel={methodLabel} />
                      </div>

                      {/* 路径（单行） */}
                      <div className="text-[11px] text-muted-foreground truncate mb-1.5">{r.path}</div>

                      {/* 主 snippet（始终显示，排版一致） */}
                      {r.snippet && (
                        <div className="text-xs text-foreground/80 line-clamp-2 mb-1">
                          {highlightSnippet(r.snippet, query)}
                        </div>
                      )}
                    </div>

                    {/* ── 多命中展开区域 ── */}
                    {hasMulti && (
                      <>
                        <div className="border-t border-border" />
                        <button
                          className="w-full px-3 py-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground hover:bg-accent/30 transition-colors cursor-pointer"
                          onClick={e => { e.stopPropagation(); toggleCard(i); }}
                        >
                          {isOpen ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                          <span>该文件有 {r.match_positions!.length} 处命中</span>
                        </button>
                        {/* 使用纯 CSS 条件渲染，不依赖 base-ui Collapsible */}
                        {isOpen && (
                          <div className="px-3 pb-3 space-y-2">
                            {r.match_positions!.map((m, j) => {
                              return (
                                <div
                                  key={j}
                                  className="p-2.5 rounded-md border border-border bg-card hover:bg-accent/20 transition-colors cursor-pointer group"
                                  onClick={e => { e.stopPropagation(); goToPage(r.path, m.line); }}
                                >
                                  <div className="flex items-center gap-2 mb-1">
                                    <Badge variant="secondary" className="text-[10px] font-normal">
                                      {m.section || '(frontmatter)'}
                                    </Badge>
                                    <span className="text-[10px] text-muted-foreground">
                                      第 {m.line} 行
                                    </span>
                                    <ScorePill score={m.score} />
                                    <ArrowUpRight className="h-3 w-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity ml-auto" />
                                  </div>
                                  <div className="text-xs text-foreground/80 line-clamp-2">
                                    {highlightSnippet(m.snippet, query)}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </>
                    )}
                  </Card>
                );
              })}

              {/* Footer — pagination + summary */}
              <div className="flex items-center justify-center gap-3 pt-2">
                <Badge variant="secondary" className="text-[10px]">
                  {methodInfo.label} · {totalMatched > 0 ? totalMatched : results.length} 条结果
                  {totalPages > 1 && ` · 第 ${page + 1}/${totalPages} 页`}
                </Badge>
                {(page > 0 || hasMore) && totalPages > 1 && (
                  <div className="flex items-center gap-1">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-6 text-[11px] px-2"
                      disabled={page === 0 || loading}
                      onClick={() => search(page - 1)}
                    >
                      上一页
                    </Button>
                    <span className="text-[10px] text-muted-foreground px-1 tabular-nums">
                      {page + 1}/{totalPages}
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-6 text-[11px] px-2"
                      disabled={!hasMore || page >= totalPages - 1 || loading}
                      onClick={() => search(page + 1)}
                    >
                      下一页
                    </Button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <EmptyState
              icon={Search}
              title="搜索知识库"
              desc={`输入关键词搜索 Wiki 页面 · 当前模式: ${methodInfo.label}`}
            />
          )}
        </div>
      </div>
    </div>
  );
}
