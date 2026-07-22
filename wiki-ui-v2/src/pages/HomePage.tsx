import { useEffect, useState } from 'react';
import {
  BookOpen, FileText, AlertTriangle, MessageSquare,
  Search, Network, Sparkles, ArrowRight, Library,
  BrainCircuit, Hash, Activity,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useNavigate } from 'react-router-dom';
import EmptyState from '@/components/shared/EmptyState';
import { fetchJson } from '@/api/client';

interface WikiStats {
  total_pages?: number;
  entities?: number;
  concepts?: number;
  sources?: number;
  broken_links?: number;
}

interface RecentPage {
  title: string;
  path: string;
  page_type: string;
  created_at: string;
}

const typeColor: Record<string, string> = {
  entity: 'bg-blue-500/10 text-blue-600 dark:text-blue-400',
  concept: 'bg-violet-500/10 text-violet-600 dark:text-violet-400',
  source: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
  query: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
  comparison: 'bg-pink-500/10 text-pink-600 dark:text-pink-400',
};

export default function HomePage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<WikiStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [recentPages, setRecentPages] = useState<RecentPage[]>([]);

  useEffect(() => {
    Promise.all([
      fetchJson<{ pages: any[] }>('/v1/pages').catch(() => ({ pages: [] as any[] })),
      fetchJson<{ broken_links?: any[] }>('/v1/lint?semantic=false').catch(() => ({})),
      fetchJson<{ pages: any[] }>('/v1/pages?sort=created_at&limit=5').catch(() => ({ pages: [] as any[] })),
    ]).then(([pagesData, lintData, recentData]) => {
      const pages = pagesData.pages || [];
      const types: Record<string, number> = {};
      pages.forEach((p: any) => { types[p.page_type] = (types[p.page_type] || 0) + 1; });
      setStats({
        total_pages: pages.length,
        entities: types.entity || 0,
        concepts: types.concept || 0,
        sources: types.source || 0,
        broken_links: (lintData.broken_links || []).length,
      });
      setRecentPages((recentData.pages || pages).slice(0, 5));
    }).finally(() => setLoading(false));
  }, []);

  const statCards = [
    {
      label: '总页面', value: stats?.total_pages ?? '—',
      icon: Library, color: 'text-blue-500', bg: 'bg-blue-500/10',
      gradient: 'from-blue-500/10 to-blue-500/5',
    },
    {
      label: '实体', value: stats?.entities ?? '—',
      icon: BrainCircuit, color: 'text-violet-500', bg: 'bg-violet-500/10',
      gradient: 'from-violet-500/10 to-violet-500/5',
    },
    {
      label: '概念', value: stats?.concepts ?? '—',
      icon: Hash, color: 'text-emerald-500', bg: 'bg-emerald-500/10',
      gradient: 'from-emerald-500/10 to-emerald-500/5',
    },
    {
      label: '引用源', value: stats?.sources ?? '—',
      icon: FileText, color: 'text-amber-500', bg: 'bg-amber-500/10',
      gradient: 'from-amber-500/10 to-amber-500/5',
    },
  ];

  const quickActions = [
    { label: '浏览知识库', desc: '查看所有 Wiki 页面', icon: BookOpen, path: '/wiki', accent: 'var(--color-type-entity)' },
    { label: 'AI 对话', desc: '与知识库对话交互', icon: MessageSquare, path: '/chat', accent: 'var(--color-type-concept)' },
    { label: '图谱探索', desc: '可视化知识关联网络', icon: Network, path: '/graph', accent: 'var(--color-type-source)' },
    { label: '检索文档', desc: '全文搜索知识内容', icon: Search, path: '/search', accent: 'var(--color-type-query)' },
  ];

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-y-auto">
      <div className="max-w-5xl mx-auto p-6 md:p-8 space-y-8">
        {/* ── Hero Section ── */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-primary/[0.03] via-primary/[0.06] to-primary/[0.01] border border-primary/5 p-8 md:p-10">
          {/* Decorative blobs */}
          <div className="absolute -top-20 -right-20 w-60 h-60 rounded-full bg-gradient-to-br from-blue-500/8 to-violet-500/5 blur-3xl" />
          <div className="absolute -bottom-16 -left-16 w-40 h-40 rounded-full bg-gradient-to-tr from-emerald-500/6 to-blue-500/4 blur-3xl" />
          <div className="relative">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-primary/70 flex items-center justify-center shadow-lg shadow-primary/20">
                <Sparkles className="h-5 w-5 text-primary-foreground" />
              </div>
              <div>
                <h1 className="text-2xl md:text-3xl font-bold tracking-tight bg-gradient-to-r from-foreground via-foreground to-foreground/70 bg-clip-text">
                  LLM Wiki
                </h1>
              </div>
            </div>
            <p className="text-sm text-muted-foreground/80 max-w-xl leading-relaxed">
              知识沉淀与智能检索系统 · 将原始资料编译为结构化 Wiki 知识库，
              支持图谱探索、语义搜索和 AI 对话。
            </p>
          </div>
        </div>

        {/* ── Stats Grid ── */}
        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[1, 2, 3, 4].map(i => (
              <Card key={i} className="rounded-xl shadow-sm border">
                <CardContent className="p-5 space-y-3">
                  <Skeleton className="h-4 w-16" />
                  <Skeleton className="h-8 w-12" />
                </CardContent>
              </Card>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {statCards.map((card, i) => (
              <Card key={i} className="relative rounded-xl shadow-sm border border-border/60 hover:shadow-lg hover:-translate-y-1 transition-all duration-300 overflow-hidden group card-hover">
                <div className={`absolute inset-0 bg-gradient-to-br ${card.gradient} opacity-0 group-hover:opacity-100 transition-opacity duration-300`} />
                <CardContent className="p-5 relative">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{card.label}</span>
                    <div className={`w-9 h-9 rounded-xl ${card.bg} flex items-center justify-center ring-1 ring-black/[0.02] transition-transform duration-200 group-hover:scale-110`}>
                      <card.icon className={`h-4.5 w-4.5 ${card.color}`} />
                    </div>
                  </div>
                  <span className={`text-2xl md:text-3xl font-bold tracking-tight ${card.color}`}>{card.value}</span>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* ── Quick Actions ── */}
        <section>
          <div className="flex items-center gap-2 mb-4">
            <div className="w-5 h-5 rounded-md bg-gradient-to-br from-primary/10 to-primary/5 flex items-center justify-center">
              <Sparkles className="h-3 w-3 text-primary" />
            </div>
            <h2 className="text-sm font-semibold text-foreground">快捷入口</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {quickActions.map((action, i) => (
              <Card
                key={i}
                className="relative rounded-xl border cursor-pointer hover:shadow-xl hover:-translate-y-1.5 active:translate-y-0 transition-all duration-300 overflow-hidden group focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 bg-card"
                onClick={() => navigate(action.path)}
                tabIndex={0}
                onKeyDown={e => { if (e.key === 'Enter') navigate(action.path); }}
              >
                {/* Top gradient strip */}
                <div
                  className="h-1 w-full rounded-t-xl transition-all duration-300 group-hover:h-1.5"
                  style={{ background: `linear-gradient(to right, ${action.accent}, color-mix(in srgb, ${action.accent} 30%, transparent))` }}
                />
                <CardContent className="p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-transform duration-200 group-hover:scale-110 group-hover:rotate-[-4deg]"
                      style={{ backgroundColor: `color-mix(in srgb, ${action.accent} 15%, transparent)` }}
                    >
                      <action.icon className="h-5 w-5" strokeWidth={1.5} style={{ color: action.accent }} />
                    </div>
                    <ArrowRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 transition-all duration-200 -translate-x-1 group-hover:translate-x-0 group-focus-visible:translate-x-0" />
                  </div>
                  <h3 className="text-base font-bold text-foreground">{action.label}</h3>
                  <p className="text-xs text-muted-foreground/60 mt-0.5">{action.desc}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* ── Recent Pages + System Status ── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Recent Pages */}
          <Card className="md:col-span-2 rounded-xl shadow-sm border hover:shadow-md transition-shadow duration-200">
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <div className="w-6 h-6 rounded-md bg-blue-500/10 flex items-center justify-center">
                    <BookOpen className="h-3.5 w-3.5 text-blue-500" />
                  </div>
                  <h2 className="text-sm font-semibold">最近页面</h2>
                </div>
                <button
                  className="text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
                  onClick={() => navigate('/wiki')}
                >
                  查看全部 →
                </button>
              </div>
              {loading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map(i => <Skeleton key={i} className="h-10 w-full rounded-md" />)}
                </div>
              ) : recentPages.length === 0 ? (
                <EmptyState icon={BookOpen} title="暂无页面" desc="导入文档后页面将自动创建" />
              ) : (
                <div className="space-y-1">
                  {recentPages.map((page, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-accent/50 cursor-pointer transition-colors group"
                      onClick={() => navigate(`/wiki?path=${encodeURIComponent(page.path || page.title)}`)}
                    >
                      <div className={`w-6 h-6 rounded-md ${typeColor[page.page_type] || 'bg-muted'} flex items-center justify-center flex-shrink-0 transition-transform duration-150 group-hover:scale-110`}>
                        <FileText className="h-3 w-3" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-sm truncate font-medium">{page.title}</p>
                        <p className="text-xs text-muted-foreground truncate">{page.path}</p>
                      </div>
                      <span className="text-[10px] text-muted-foreground flex-shrink-0">
                        {page.created_at?.slice(0, 10) || ''}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* System Status */}
          <Card className="rounded-xl shadow-sm border hover:shadow-md transition-shadow duration-200">
            <CardContent className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <div className="w-6 h-6 rounded-md bg-green-500/10 flex items-center justify-center">
                  <Activity className="h-3.5 w-3.5 text-green-500" />
                </div>
                <h2 className="text-sm font-semibold">系统状态</h2>
              </div>
              <div className="space-y-2.5">
                <div className="flex items-center justify-between py-2.5 px-3 rounded-lg bg-gradient-to-r from-green-500/5 to-transparent border border-green-500/10">
                  <div className="flex items-center gap-2.5">
                    <span className="w-2 h-2 rounded-full bg-green-500 shadow-sm shadow-green-500/40" />
                    <span className="text-xs text-muted-foreground">后端服务</span>
                  </div>
                  <span className="text-xs font-medium text-green-600 dark:text-green-400">运行中</span>
                </div>
                <div className="flex items-center justify-between py-2.5 px-3 rounded-lg bg-muted/30">
                  <div className="flex items-center gap-2.5">
                    <Library className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs text-muted-foreground">已索引</span>
                  </div>
                  <span className="text-xs font-medium">{stats?.total_pages ?? '—'} 页</span>
                </div>
                {stats && stats.broken_links !== undefined && (
                  <div className={`flex items-center justify-between py-2.5 px-3 rounded-lg ${stats.broken_links > 0 ? 'bg-gradient-to-r from-amber-500/5 to-transparent border border-amber-500/10' : 'bg-muted/30'}`}>
                    <div className="flex items-center gap-2.5">
                      <AlertTriangle className={`h-3.5 w-3.5 ${stats.broken_links > 0 ? 'text-amber-500' : 'text-muted-foreground'}`} />
                      <span className="text-xs text-muted-foreground">断链</span>
                    </div>
                    <span className={`text-xs font-medium ${stats.broken_links > 0 ? 'text-amber-500' : ''}`}>
                      {stats.broken_links}
                    </span>
                  </div>
                )}
              </div>
              <div className="mt-4 pt-4 border-t border-border">
                <button
                  className="w-full text-xs text-muted-foreground hover:text-foreground transition-colors text-center cursor-pointer"
                  onClick={() => navigate('/health')}
                >
                  查看详细状态 →
                </button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ── Footer info ── */}
        <div className="text-center text-[10px] text-muted-foreground/40 pb-4 tracking-wider">
          LLM Wiki · 知识沉淀管理系统
        </div>
      </div>
    </div>
  );
}
