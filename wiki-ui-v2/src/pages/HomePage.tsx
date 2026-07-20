import { useEffect, useState } from 'react';
import {
  BookOpen, FileText, AlertTriangle, MessageSquare,
  Search, Network, CheckCircle2, Sparkles, ArrowRight, Library,
  BrainCircuit, Hash,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useNavigate } from 'react-router-dom';

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
      fetch('/v1/pages').then(r => r.json()).catch(() => ({ pages: [] })),
      fetch('/v1/lint?semantic=false').then(r => r.json()).catch(() => ({})),
      fetch('/v1/pages?sort=created_at&limit=5').then(r => r.json()).catch(() => ({ pages: [] })),
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
    },
    {
      label: '实体', value: stats?.entities ?? '—',
      icon: BrainCircuit, color: 'text-violet-500', bg: 'bg-violet-500/10',
    },
    {
      label: '概念', value: stats?.concepts ?? '—',
      icon: Hash, color: 'text-emerald-500', bg: 'bg-emerald-500/10',
    },
    {
      label: '引用源', value: stats?.sources ?? '—',
      icon: FileText, color: 'text-amber-500', bg: 'bg-amber-500/10',
    },
  ];

  const quickActions = [
    { label: '浏览知识库', desc: '查看所有 Wiki 页面', icon: BookOpen, path: '/wiki', accent: 'var(--color-type-entity)' },
    { label: 'AI 对话', desc: '与知识库对话交互', icon: MessageSquare, path: '/chat', accent: 'var(--color-type-concept)' },
    { label: '图谱探索', desc: '可视化知识关联网络', icon: Network, path: '/graph', accent: 'var(--color-type-source)' },
    { label: '检索文档', desc: '全文搜索知识内容', icon: Search, path: '/search', accent: 'var(--color-type-query)' },
  ];

  return (
    <div className="flex-1 overflow-y-auto">
      <div className="max-w-5xl mx-auto p-6 md:p-8 space-y-8">
        {/* ── Hero / Welcome ── */}
        <div className="space-y-1">
          <h1 className="text-2xl md:text-3xl font-bold tracking-tight text-foreground">
            LLM Wiki
          </h1>
          <p className="text-sm text-muted-foreground">
            知识库仪表盘 · 知识沉淀与智能检索系统
          </p>
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
              <Card key={i} className="rounded-xl shadow-sm border border-border/60 hover:shadow-md transition-all duration-200 hover:-translate-y-0.5">
                <CardContent className="p-5">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{card.label}</span>
                    <div className={`w-8 h-8 rounded-lg ${card.bg} flex items-center justify-center`}>
                      <card.icon className={`h-4 w-4 ${card.color}`} />
                    </div>
                  </div>
                  <span className="text-2xl md:text-3xl font-bold tracking-tight">{card.value}</span>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* ── Quick Actions ── */}
        <section>
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold text-foreground">快捷入口</h2>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {quickActions.map((action, i) => (
              <Card
                key={i}
                className="relative rounded-xl border cursor-pointer hover:shadow-lg hover:-translate-y-1 active:translate-y-0 transition-all duration-200 overflow-hidden group focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 bg-card"
                onClick={() => navigate(action.path)}
              >
                {/* Top gradient strip — subtle accent */}
                <div
                  className="h-1 w-full rounded-t-xl"
                  style={{ background: `linear-gradient(to right, color-mix(in srgb, ${action.accent} 25%, transparent), transparent)` }}
                />
                <CardContent className="p-5">
                  <div className="flex items-start justify-between mb-3">
                    <div
                      className="w-10 h-10 rounded-xl flex items-center justify-center shrink-0"
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
          <Card className="md:col-span-2 rounded-xl shadow-sm border">
            <CardContent className="p-5">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <BookOpen className="h-4 w-4 text-muted-foreground" />
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
                <div className="text-center py-6">
                  <BookOpen className="h-8 w-8 mx-auto mb-2 text-muted-foreground/30" />
                  <p className="text-sm text-muted-foreground">暂无页面</p>
                  <p className="text-xs text-muted-foreground/60 mt-1">导入文档后页面将自动创建</p>
                </div>
              ) : (
                <div className="space-y-1">
                  {recentPages.map((page, i) => (
                    <div
                      key={i}
                      className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-accent/50 cursor-pointer transition-colors group"
                      onClick={() => navigate(`/wiki?path=${encodeURIComponent(page.path || page.title)}`)}
                    >
                      <div className={`w-6 h-6 rounded-md ${typeColor[page.page_type] || 'bg-muted'} flex items-center justify-center flex-shrink-0`}>
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
          <Card className="rounded-xl shadow-sm border">
            <CardContent className="p-5">
              <div className="flex items-center gap-2 mb-4">
                <CheckCircle2 className="h-4 w-4 text-green-500" />
                <h2 className="text-sm font-semibold">系统状态</h2>
              </div>
              <div className="space-y-3">
                <div className="flex items-center justify-between py-2 px-3 rounded-lg bg-green-500/5 border border-green-500/10">
                  <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-green-500" />
                    <span className="text-xs text-muted-foreground">后端服务</span>
                  </div>
                  <span className="text-xs font-medium text-green-600 dark:text-green-400">运行中</span>
                </div>
                <div className="flex items-center justify-between py-2 px-3 rounded-lg bg-muted/50">
                  <div className="flex items-center gap-2">
                    <Library className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="text-xs text-muted-foreground">已索引</span>
                  </div>
                  <span className="text-xs font-medium">{stats?.total_pages ?? '—'} 页</span>
                </div>
                {stats && stats.broken_links !== undefined && (
                  <div className={`flex items-center justify-between py-2 px-3 rounded-lg ${stats.broken_links > 0 ? 'bg-amber-500/5 border border-amber-500/10' : 'bg-muted/50'}`}>
                    <div className="flex items-center gap-2">
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
        <div className="text-center text-[10px] text-muted-foreground/40 pb-4">
          LLM Wiki · 知识沉淀管理系统
        </div>
      </div>
    </div>
  );
}
