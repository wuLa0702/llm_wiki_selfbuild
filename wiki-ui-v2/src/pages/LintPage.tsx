import { useEffect, useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle, CheckCircle, FileWarning, RefreshCw,
  BookOpen, GitBranch, HelpCircle, FileEdit, BrainCircuit,
  Copy, Plus, ChevronLeft, ChevronRight, Network,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from '@/components/ui/tooltip';
import { showToast } from '@/components/shared/Toast';
import EmptyState from '@/components/shared/EmptyState';

/* ─── Types ─── */

interface BrokenLink { source_page: string; broken_target: string; }
interface Contradiction {
  page_a: string; page_b: string; description: string;
  confidence?: string;
}
interface KnowledgeGap {
  topic: string; description: string; mentioned_in?: string[];
}
interface ShallowPage {
  page: string; reason: string; suggestion?: string;
}
interface LintResult {
  broken_links?: BrokenLink[];
  orphan_pages?: string[];
  index_gaps?: string[];
  contradictions?: Contradiction[];
  knowledge_gaps?: KnowledgeGap[];
  shallow_pages?: ShallowPage[];
  health_score?: number;
  summary?: string;
  cached?: boolean;
}

/* ─── Constants ─── */

const PAGE_SIZE = 20;

const DEDUCTION_RULES = [
  { key: '断链', rule: '每条 −5 分', icon: AlertTriangle, color: 'text-red-500' },
  { key: '孤页', rule: '每条 −10 分', icon: FileWarning, color: 'text-amber-500' },
  { key: 'Index 缺口', rule: '每条 −3 分', icon: BookOpen, color: 'text-blue-500' },
];

interface Rating { label: string; color: string; bg: string; }
function getRating(score: number): Rating {
  if (score >= 90) return { label: '优秀', color: 'text-green-600 dark:text-green-400', bg: 'bg-green-500/10 border-green-200 dark:border-green-800' };
  if (score >= 70) return { label: '良好', color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-500/10 border-blue-200 dark:border-blue-800' };
  if (score >= 60) return { label: '一般', color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-500/10 border-amber-200 dark:border-amber-800' };
  return { label: '危险', color: 'text-red-600 dark:text-red-400', bg: 'bg-red-500/10 border-red-200 dark:border-red-800' };
}

const ISSUE_STYLE: Record<string, { border: string; icon: typeof AlertTriangle; label: string; desc: string }> = {
  broken: { border: 'border-l-red-500', icon: AlertTriangle, label: '断链', desc: '引用不存在页面的链接' },
  orphan: { border: 'border-l-amber-500', icon: FileWarning, label: '孤立页面', desc: '无入链，未被任何页面引用' },
  gap: { border: 'border-l-blue-500', icon: BookOpen, label: 'Index 缺口', desc: '存在于 wiki/ 但未在 index.md 列出' },
};

/* ─── Helpers ─── */

function scoreColor(score: number): string {
  if (score >= 80) return 'text-green-600 dark:text-green-400';
  if (score >= 50) return 'text-amber-600 dark:text-amber-400';
  return 'text-red-600 dark:text-red-400';
}

/** From backend scoring: 断链×5 + 孤页×10 + 缺口×3 */
function buildIssuesText(r: LintResult): string {
  const lines: string[] = [`Wiki 健康检查报告 — 评分 ${r.health_score ?? 'N/A'}/100\n`];
  if (r.broken_links?.length) {
    lines.push(`\n## 断链 (${r.broken_links.length})`);
    r.broken_links.forEach(l => lines.push(`  ${l.source_page} → ${l.broken_target}`));
  }
  if (r.orphan_pages?.length) {
    lines.push(`\n## 孤立页面 (${r.orphan_pages.length})`);
    r.orphan_pages.forEach(p => lines.push(`  ${p}`));
  }
  if (r.index_gaps?.length) {
    lines.push(`\n## Index 缺口 (${r.index_gaps.length})`);
    r.index_gaps.forEach(p => lines.push(`  ${p}`));
  }
  if (r.contradictions?.length) {
    lines.push(`\n## 内容矛盾 (${r.contradictions.length})`);
    r.contradictions.forEach(c => lines.push(`  ${c.page_a} ↔ ${c.page_b}: ${c.description}`));
  }
  if (r.knowledge_gaps?.length) {
    lines.push(`\n## 知识缺口 (${r.knowledge_gaps.length})`);
    r.knowledge_gaps.forEach(g => lines.push(`  ${g.topic}: ${g.description}`));
  }
  if (r.shallow_pages?.length) {
    lines.push(`\n## 浅页面 (${r.shallow_pages.length})`);
    r.shallow_pages.forEach(s => lines.push(`  ${s.page}: ${s.reason}`));
  }
  lines.push(`\n---\nLLM Wiki 自动生成`);
  return lines.join('\n');
}

/* ─── Stat Card ─── */

function StatCard({
  label, value, unit, icon: Icon, color, deduction, rating,
}: {
  label: string; value: number | string; unit?: string;
  icon: typeof AlertTriangle; color: string;
  deduction?: string; rating?: Rating;
}) {
  return (
    <Card>
      <CardContent className="p-4">
        <Tooltip>
          <TooltipTrigger>
            <div className="cursor-help">
              <p className="text-xs text-muted-foreground mb-1 flex items-center gap-1">
                <Icon className={`h-3 w-3 ${color}`} />
                {label}
              </p>
              <p className={`text-2xl font-bold ${color}`}>
                {value}{unit && <span className="text-lg ml-0.5">{unit}</span>}
              </p>
              {rating && (
                <span className={`inline-block mt-1 text-[10px] font-semibold px-1.5 py-0.5 rounded ${rating.bg} ${rating.color}`}>
                  {rating.label}
                </span>
              )}
              {deduction && (
                <p className="text-[10px] text-muted-foreground/60 mt-1">{deduction}</p>
              )}
            </div>
          </TooltipTrigger>
          <TooltipContent side="bottom" className="max-w-[200px] text-xs">
            <p className="font-medium mb-1">{label} 扣分规则</p>
            {deduction ? <p>{deduction}</p> : <p>无扣分</p>}
            <p className="text-muted-foreground mt-1">分数越低表示知识库质量越差</p>
          </TooltipContent>
        </Tooltip>
      </CardContent>
    </Card>
  );
}

/* ─── Broken Links List (with pagination + quick create) ─── */

function BrokenLinksSection({
  links, page, onPageChange, onFix,
}: {
  links: BrokenLink[]; page: number; onPageChange: (p: number) => void; onFix: () => void;
}) {
  const navigate = useNavigate();
  const totalPages = Math.max(1, Math.ceil(links.length / PAGE_SIZE));
  const start = (page - 1) * PAGE_SIZE;
  const paged = links.slice(start, start + PAGE_SIZE);

  if (links.length === 0) return null;

  return (
    <Card className="border-l-3 border-l-red-500">
      <CardContent className="p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-destructive" />
            <h2 className="text-sm font-semibold">断链 ({links.length})</h2>
            <span className="text-[10px] text-muted-foreground/60">引用不存在页面的链接</span>
          </div>
          <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={onFix}>
            <Plus className="h-3 w-3" />
            修复全部
          </Button>
        </div>

        <div className="space-y-1">
          {/* Header */}
          <div className="grid grid-cols-[1fr_auto_1fr_auto] gap-2 px-2 py-1 text-[10px] text-muted-foreground/50 font-medium">
            <span>来源文档</span>
            <span />
            <span>失效目标</span>
            <span className="w-14" />
          </div>

          {paged.map((link, i) => (
            <div
              key={i}
              className="grid grid-cols-[1fr_auto_1fr_auto] gap-2 items-center p-2 rounded bg-muted/50 text-xs hover:bg-muted/80 transition-colors"
            >
              <button
                className="text-left truncate text-destructive font-medium hover:underline cursor-pointer"
                onClick={() => {
                  const pp = link.source_page.replace(/\.md$/, '');
                  navigate(`/wiki/${encodeURIComponent(pp)}`);
                }}
                title={link.source_page}
              >
                {link.source_page}
              </button>
              <span className="text-muted-foreground/40 shrink-0">→</span>
              <span className="truncate text-muted-foreground" title={link.broken_target}>
                {link.broken_target}
              </span>
              <span className="w-14 text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 text-[10px] gap-0.5 px-1.5"
                  onClick={onFix}
                >
                  <Plus className="h-2.5 w-2.5" />
                  创建
                </Button>
              </span>
            </div>
          ))}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-3 pt-2 border-t border-border">
            <span className="text-[10px] text-muted-foreground/50">
              共 {links.length} 条，第 {page}/{totalPages} 页
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost" size="sm" className="h-6 w-6 p-0"
                disabled={page <= 1}
                onClick={() => onPageChange(page - 1)}
              >
                <ChevronLeft className="h-3 w-3" />
              </Button>
              {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                <Button
                  key={p}
                  variant={p === page ? 'default' : 'ghost'}
                  size="sm"
                  className="h-6 min-w-6 px-1 text-[10px]"
                  onClick={() => onPageChange(p)}
                >
                  {p}
                </Button>
              ))}
              <Button
                variant="ghost" size="sm" className="h-6 w-6 p-0"
                disabled={page >= totalPages}
                onClick={() => onPageChange(page + 1)}
              >
                <ChevronRight className="h-3 w-3" />
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

/* ─── Issue Item Card (orphans, gaps — compact tag display) ─── */

function IssueTagList({
  items, type, onNavigate,
}: {
  items: string[]; type: 'orphan' | 'gap'; onNavigate?: (path: string) => void;
}) {
  const style = ISSUE_STYLE[type];
  const Icon = style.icon;

  if (items.length === 0) return null;

  return (
    <Card className={`border-l-3 ${style.border}`}>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 mb-3">
          <Icon className={`h-4 w-4 ${type === 'orphan' ? 'text-amber-500' : 'text-blue-500'}`} />
          <h2 className="text-sm font-semibold">{style.label} ({items.length})</h2>
          <span className="text-[10px] text-muted-foreground/60">{style.desc}</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {items.map(p => (
            onNavigate ? (
              <button key={p} className="cursor-pointer" onClick={() => onNavigate(p.replace(/\.md$/, ''))}>
                <Badge variant="outline" className="text-[10px] hover:bg-accent transition-colors">
                  {p}
                </Badge>
              </button>
            ) : (
              <Badge key={p} variant="outline" className="text-[10px]">{p}</Badge>
            )
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

/* ─── Main Page ─── */

const STORAGE_KEY = 'lint-page-state';

export default function LintPage() {
  const navigate = useNavigate();
  const [result, setResult] = useState<LintResult | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [isSemantic, setIsSemantic] = useState(false);
  const [brokenPage, setBrokenPage] = useState(() => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved) return JSON.parse(saved).brokenPage || 1;
    } catch { /* ignore */ }
    return 1;
  });
  const [fixing, setFixing] = useState(false);
  const [lastChecked, setLastChecked] = useState<string>('');
  const scrollRef = useRef<HTMLDivElement>(null);
  const resultRef = useRef<LintResult | null>(null);
  resultRef.current = result;

  /* ─── Data fetching ─── */

  const runLint = useCallback(async (semantic = false, isManual = false) => {
    const isInitial = resultRef.current === null;
    if (isInitial) setInitialLoading(true);
    else if (isManual) setRefreshing(true);
    setIsSemantic(semantic);
    try {
      const r = await fetch(`/v1/lint?semantic=${semantic}`);
      const d = await r.json();
      setResult(d);
      setLastChecked(new Date().toLocaleTimeString());
      // Reset pagination only on manual or initial load (not silent poll)
      if (isManual || isInitial) setBrokenPage(1);
      if (isManual) showToast('检查完成', 'success');
    } catch {
      if (isManual) showToast('检查失败', 'error');
      // 静默轮询失败不打扰用户
    } finally {
      setInitialLoading(false);
      setRefreshing(false);
    }
  }, []);

  // 首次加载 + 30s 静默轮询
  useEffect(() => {
    runLint(false);
    const id = setInterval(() => runLint(isSemantic, false), 30_000);
    return () => clearInterval(id);
  }, [runLint, isSemantic]);

  /* ─── Copy all issues ─── */

  const copyAll = useCallback(() => {
    if (!result) return;
    const text = buildIssuesText(result);
    navigator.clipboard.writeText(text).then(
      () => showToast('已复制问题清单', 'success'),
      () => showToast('复制失败', 'error'),
    );
  }, [result]);

  /* ─── Quick fix ─── */

  const runFix = useCallback(async () => {
    setFixing(true);
    try {
      const r = await fetch('/v1/lint/fix', { method: 'POST' });
      const d = await r.json();
      showToast(d.message || '修复完成', 'success');
      // Refresh lint results (manual = true 以显示 toast + 重置分页)
      await runLint(isSemantic, true);
    } catch {
      showToast('修复请求失败', 'error');
    }
    setFixing(false);
  }, [isSemantic, runLint]);

  /* ─── State preservation ─── */

  useEffect(() => {
    const save = () => {
      try {
        sessionStorage.setItem(STORAGE_KEY, JSON.stringify({
          brokenPage,
          scrollY: scrollRef.current?.scrollTop ?? 0,
        }));
      } catch { /* quota? */ }
    };
    // Save before unload / tab switch
    window.addEventListener('beforeunload', save);
    return () => {
      save();
      window.removeEventListener('beforeunload', save);
    };
  }, [brokenPage]);

  // Restore scroll on mount
  useEffect(() => {
    try {
      const saved = sessionStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.scrollY && scrollRef.current) {
          requestAnimationFrame(() => {
            scrollRef.current!.scrollTop = parsed.scrollY;
          });
        }
      }
    } catch { /* ignore */ }
  }, []);

  /* ─── Derived data ─── */

  const score = result?.health_score ?? -1;
  const rating = score >= 0 ? getRating(score) : null;
  const links = result?.broken_links || [];
  const orphans = result?.orphan_pages || [];
  const gaps = result?.index_gaps || [];
  const contradictions = result?.contradictions || [];
  const knowledgeGaps = result?.knowledge_gaps || [];
  const shallowPages = result?.shallow_pages || [];
  const hasIssues = links.length > 0 || orphans.length > 0 || gaps.length > 0
    || contradictions.length > 0 || knowledgeGaps.length > 0 || shallowPages.length > 0;

  /* ─── Render ─── */

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-y-auto p-6" ref={scrollRef}>
      <div className="max-w-4xl mx-auto space-y-5">

        {/* ── Header + Batch action bar ── */}
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <h1 className="text-xl font-bold">Wiki 健康检查</h1>
            <p className="text-sm text-muted-foreground flex items-center gap-2">
              检测断链、孤立页面、Index 缺口等质量问题
              {lastChecked && (
                <span className="text-[10px] text-muted-foreground/50">· 上次检查 {lastChecked}</span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Button
              variant="outline" size="sm"
              onClick={() => runLint(isSemantic, true)}
              disabled={refreshing}
            >
              <RefreshCw className={`h-3.5 w-3.5 mr-1 ${refreshing ? 'animate-spin' : ''}`} />
              {refreshing ? '检查中...' : '刷新检测'}
            </Button>
            <Button
              variant="outline" size="sm"
              onClick={copyAll}
              disabled={!result || initialLoading || refreshing}
            >
              <Copy className="h-3.5 w-3.5 mr-1" />
              复制问题清单
            </Button>
            <Button
              size="sm"
              onClick={() => runLint(!isSemantic, true)}
              disabled={refreshing}
              variant={isSemantic ? 'default' : 'secondary'}
            >
              <BrainCircuit className={`h-3.5 w-3.5 mr-1 ${refreshing ? 'animate-spin' : ''}`} />
              {isSemantic ? '语义检查 ✓' : '语义检查'}
            </Button>
          </div>
        </div>

        {initialLoading ? (
          /* ── Skeleton loading ── */
          <div className="space-y-3">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-24 rounded-lg" />)}
            </div>
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-32 w-full rounded-lg" />
            <Skeleton className="h-32 w-full rounded-lg" />
          </div>
        ) : result && score >= 0 ? (
          <>
            {/* ── Rating badge + score summary ── */}
            {result.summary && !hasIssues && (
              <Card className={`border-l-3 ${score >= 80 ? 'border-l-green-500' : score >= 60 ? 'border-l-amber-500' : 'border-l-red-500'}`}>
                <CardContent className="p-4 flex items-center gap-3">
                  <CheckCircle className={`h-6 w-6 shrink-0 ${score >= 80 ? 'text-green-500' : 'text-amber-500'}`} />
                  <div>
                    <p className="text-sm font-medium">{result.summary}</p>
                    {rating && (
                      <span className={`inline-block mt-1 text-[10px] font-semibold px-1.5 py-0.5 rounded ${rating.bg} ${rating.color}`}>
                        {rating.label}
                      </span>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* ── 4 Stat Cards ── */}
            <div className={`grid grid-cols-2 md:grid-cols-4 gap-3 ${!hasIssues ? 'opacity-80' : ''}`}>
              <StatCard
                label="健康评分"
                value={score}
                unit="/100"
                icon={CheckCircle}
                color={scoreColor(score)}
                rating={rating || undefined}
              />
              <StatCard
                label="断链"
                value={links.length}
                icon={AlertTriangle}
                color="text-red-500"
                deduction={`每条 -5 分${links.length > 0 ? `，共 -${links.length * 5} 分` : ''}`}
              />
              <StatCard
                label="孤立页面"
                value={orphans.length}
                icon={FileWarning}
                color="text-amber-500"
                deduction={`每条 -10 分${orphans.length > 0 ? `，共 -${orphans.length * 10} 分` : ''}`}
              />
              <StatCard
                label="Index 缺口"
                value={gaps.length}
                icon={BookOpen}
                color="text-blue-500"
                deduction={`每条 -3 分${gaps.length > 0 ? `，共 -${gaps.length * 3} 分` : ''}`}
              />
            </div>

            {/* ── Deduction rules legend ── */}
            <div className="flex items-center gap-4 flex-wrap text-[10px] text-muted-foreground/50 px-1">
              <span className="font-medium text-foreground/40">扣分规则：</span>
              {DEDUCTION_RULES.map(r => (
                <span key={r.key} className="flex items-center gap-1">
                  <r.icon className="h-2.5 w-2.5" />
                  {r.key} {r.rule}
                </span>
              ))}
            </div>

            {/* ── Issue section cards ── */}
            {links.length > 0 && (
              <BrokenLinksSection
                links={links}
                page={brokenPage}
                onPageChange={setBrokenPage}
                onFix={runFix}
              />
            )}

            {orphans.length > 0 && (
              <IssueTagList
                items={orphans}
                type="orphan"
                onNavigate={(p) => navigate(`/wiki/${encodeURIComponent(p)}`)}
              />
            )}

            {gaps.length > 0 && (
              <IssueTagList
                items={gaps}
                type="gap"
                onNavigate={(p) => navigate(`/wiki/${encodeURIComponent(p)}`)}
              />
            )}

            {/* ── Semantic sections ── */}
            {contradictions.length > 0 && (
              <Card className="border-l-3 border-l-purple-500">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <GitBranch className="h-4 w-4 text-purple-500" />
                    <h2 className="text-sm font-semibold">内容矛盾 ({contradictions.length})</h2>
                    <Badge variant="outline" className="text-[10px]">语义</Badge>
                    <span className="text-[10px] text-muted-foreground/60">同一知识点存在冲突的描述</span>
                  </div>
                  <div className="space-y-2">
                    {contradictions.map((c, i) => (
                      <div key={i} className="p-2.5 rounded bg-muted/50 text-xs space-y-1">
                        <div className="flex items-center gap-2">
                          <button
                            className="text-purple-600 dark:text-purple-400 font-medium hover:underline cursor-pointer"
                            onClick={() => navigate(`/wiki/${encodeURIComponent(c.page_a.replace(/\.md$/, ''))}`)}
                          >
                            {c.page_a}
                          </button>
                          <span className="text-muted-foreground">↔</span>
                          <button
                            className="text-purple-600 dark:text-purple-400 font-medium hover:underline cursor-pointer"
                            onClick={() => navigate(`/wiki/${encodeURIComponent(c.page_b.replace(/\.md$/, ''))}`)}
                          >
                            {c.page_b}
                          </button>
                          {c.confidence && (
                            <Badge variant="outline" className={`text-[9px] ${c.confidence === 'high' ? 'border-red-300 text-red-500' : ''}`}>
                              {c.confidence === 'high' ? '高置信' : '低置信'}
                            </Badge>
                          )}
                        </div>
                        <p className="text-muted-foreground">{c.description}</p>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {knowledgeGaps.length > 0 && (
              <Card className="border-l-3 border-l-cyan-500">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <HelpCircle className="h-4 w-4 text-cyan-500" />
                    <h2 className="text-sm font-semibold">知识缺口 ({knowledgeGaps.length})</h2>
                    <Badge variant="outline" className="text-[10px]">语义</Badge>
                    <span className="text-[10px] text-muted-foreground/60">应该覆盖但尚未编写的内容</span>
                  </div>
                  <div className="space-y-2">
                    {knowledgeGaps.map((g, i) => (
                      <div key={i} className="p-2.5 rounded bg-muted/50 text-xs space-y-1">
                        <p className="font-medium text-cyan-700 dark:text-cyan-300">{g.topic}</p>
                        <p className="text-muted-foreground">{g.description}</p>
                        {g.mentioned_in && g.mentioned_in.length > 0 && (
                          <div className="flex items-center gap-1 flex-wrap">
                            <span className="text-muted-foreground">提及于：</span>
                            {g.mentioned_in.map(m => (
                              <button
                                key={m}
                                className="cursor-pointer"
                                onClick={() => navigate(`/wiki/${encodeURIComponent(m.replace(/\.md$/, ''))}`)}
                              >
                                <Badge variant="outline" className="text-[9px] hover:bg-accent transition-colors">{m}</Badge>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {shallowPages.length > 0 && (
              <Card className="border-l-3 border-l-orange-500">
                <CardContent className="p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <FileEdit className="h-4 w-4 text-orange-500" />
                    <h2 className="text-sm font-semibold">浅页面 ({shallowPages.length})</h2>
                    <Badge variant="outline" className="text-[10px]">语义</Badge>
                    <span className="text-[10px] text-muted-foreground/60">内容过于简短，需要扩充</span>
                  </div>
                  <div className="space-y-2">
                    {shallowPages.map((s, i) => (
                      <div key={i} className="p-2.5 rounded bg-muted/50 text-xs space-y-1">
                        <button
                          className="font-medium text-orange-700 dark:text-orange-300 hover:underline cursor-pointer"
                          onClick={() => navigate(`/wiki/${encodeURIComponent(s.page.replace(/\.md$/, ''))}`)}
                        >
                          {s.page}
                        </button>
                        <p className="text-muted-foreground">{s.reason}</p>
                        {s.suggestion && (
                          <p className="text-blue-600 dark:text-blue-400">建议：{s.suggestion}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* ── Empty state (no issues at all) ── */}
            {!hasIssues && (
              <EmptyState
                icon={CheckCircle}
                title="知识库状态健康"
                desc="未发现断链、孤立页面、Index 缺口或语义问题"
              />
            )}

            {/* ── Fixing progress ── */}
            {fixing && (
              <Card className="border-l-3 border-l-blue-500">
                <CardContent className="p-4 text-sm flex items-center gap-2">
                  <RefreshCw className="h-4 w-4 animate-spin text-blue-500" />
                  <span>正在修复断链...</span>
                </CardContent>
              </Card>
            )}
          </>
        ) : result && score < 0 ? (
          /* ── Fallback for old API without health_score ── */
          <Card>
            <CardContent className="p-4 text-sm">
              {result.summary || 'Lint 检查完成'}
            </CardContent>
          </Card>
        ) : (
          /* ── No data / error ── */
          <EmptyState
            icon={Network}
            title="暂无检查数据"
            desc="点击「刷新检测」运行 Wiki 健康检查"
            action={{ label: '运行检查', onClick: () => runLint(false) }}
          />
        )}
      </div>
    </div>
  );
}
