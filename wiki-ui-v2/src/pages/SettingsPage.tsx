import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Sun, Moon, Monitor, Minus, Plus, Save, Palette, SlidersHorizontal, Brain, Cpu, Wifi, Activity, Eye, Play, Square } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { showToast } from '@/components/shared/Toast';
import { useTheme } from '@/hooks/useTheme';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Package, Timer, FileText, Network as NetworkIcon, ListTodo, AlertCircle, CheckCircle2 } from 'lucide-react';

const settingsTabs = [
  { key: 'interface', label: '界面', icon: Palette },
  { key: 'general', label: '通用', icon: SlidersHorizontal },
  { key: 'llm', label: 'LLM 模型', icon: Brain },
  { key: 'embedding', label: '向量嵌入', icon: Cpu },
  { key: 'network', label: '网络', icon: Wifi },
  { key: 'watcher', label: '资料监控', icon: Eye },
  { key: 'health', label: '健康检查', icon: Activity },
];

export default function SettingsPage() {
  const { tab: activeTab } = useParams<{ tab: string }>();
  const navigate = useNavigate();
  const tab = activeTab || 'interface';

  return (
    <div className="flex flex-1 min-h-0">
      {/* Tab sidebar */}
      <div className="w-52 flex-shrink-0 border-r border-border bg-card">
        <div className="py-2">
          {settingsTabs.map(t => {
            const Icon = t.icon;
            return (
              <button
                key={t.key}
                className={`w-full flex items-center gap-2.5 px-4 py-2 text-sm cursor-pointer transition-colors ${
                  tab === t.key
                    ? 'text-foreground bg-accent border-l-3 border-primary font-medium'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent/50 border-l-3 border-transparent'
                }`}
                onClick={() => navigate(`/settings/${t.key}`)}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span>{t.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {tab === 'interface' && <InterfaceSettings />}
        {tab === 'general' && <GeneralSettings />}
        {tab === 'llm' && <LLMSettings />}
        {tab === 'embedding' && <Placeholder title="向量嵌入" desc="向量嵌入配置（待实现）" />}
        {tab === 'network' && <Placeholder title="网络" desc="网络配置（待实现）" />}
        {tab === 'watcher' && <WatcherSettings />}
        {tab === 'health' && <HealthSettings />}
      </div>
    </div>
  );
}

function InterfaceSettings() {
  const { theme, setTheme } = useTheme();
  const [lang, setLang] = useState<'zh' | 'en'>(() => (localStorage.getItem('ui_lang') as 'zh' | 'en') || 'zh');
  const [zoom, setZoom] = useState(() => parseInt(localStorage.getItem('ui_zoom') || '100'));

  useEffect(() => {
    const clamped = Math.max(50, Math.min(200, zoom));
    document.documentElement.style.fontSize = `${clamped}%`;
  }, [zoom]);

  const save = () => {
    localStorage.setItem('ui_lang', lang);
    localStorage.setItem('ui_zoom', String(Math.max(50, Math.min(200, zoom))));
    showToast('设置已保存', 'success');
  };

  return (
    <div className="p-6 flex flex-col min-h-0 max-w-2xl">
      <h2 className="text-lg font-semibold mb-1">界面</h2>
      <p className="text-sm text-muted-foreground mb-6">界面语言和外观样式</p>

      {/* Language */}
      <section className="mb-6">
        <h3 className="text-sm font-medium mb-2">UI 语言</h3>
        <div className="flex gap-2">
          {[
            { value: 'zh', label: '中文' },
            { value: 'en', label: 'English' },
          ].map(opt => (
            <button
              key={opt.value}
              className={`px-4 py-2 text-sm rounded-md cursor-pointer ${
                lang === opt.value
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border bg-secondary text-secondary-foreground hover:bg-accent'
              }`}
              onClick={() => setLang(opt.value as 'zh' | 'en')}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </section>

      {/* Theme */}
      <section className="mb-6">
        <h3 className="text-sm font-medium mb-2">主题</h3>
        <div className="flex gap-2">
          {[
            { value: 'light', label: '浅色', icon: Sun },
            { value: 'dark', label: '深色', icon: Moon },
            { value: 'system', label: '跟随系统', icon: Monitor },
          ].map(opt => (
            <button
              key={opt.value}
              className={`flex items-center gap-1.5 px-4 py-2 text-sm rounded-md cursor-pointer ${
                theme === opt.value
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border bg-secondary text-secondary-foreground hover:bg-accent'
              }`}
              onClick={() => setTheme(opt.value as 'light' | 'dark' | 'system')}
            >
              <opt.icon className="h-4 w-4" />
              {opt.label}
            </button>
          ))}
        </div>
      </section>

      {/* Zoom */}
      <section className="mb-6">
        <h3 className="text-sm font-medium mb-2">界面缩放</h3>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={() => setZoom(z => Math.max(50, z - 10))}>
            <Minus className="h-3 w-3" />
          </Button>
          <div className="flex items-center gap-1 px-3 py-1.5 border border-border rounded-md bg-secondary">
            <input
              className="w-12 bg-transparent border-none text-sm text-center outline-none"
              value={zoom}
              onChange={e => {
                const v = parseInt(e.target.value);
                if (!isNaN(v)) setZoom(Math.max(50, Math.min(200, v)));
              }}
            />
            <span className="text-xs text-muted-foreground">%</span>
          </div>
          <Button variant="outline" size="icon" onClick={() => setZoom(z => Math.min(200, z + 10))}>
            <Plus className="h-3 w-3" />
          </Button>
        </div>
      </section>

      <div className="flex-1" />
      <div className="flex items-center justify-between pt-4 border-t border-border">
        <span className="text-xs text-muted-foreground">改动需要保存后生效</span>
        <Button onClick={save} size="sm">
          <Save className="h-3.5 w-3.5 mr-1" /> 保存
        </Button>
      </div>
    </div>
  );
}

function GeneralSettings() {
  return (
    <div className="p-6 max-w-2xl">
      <h2 className="text-lg font-semibold mb-1">通用设置</h2>
      <p className="text-sm text-muted-foreground mb-6">基础配置项</p>
      <p className="text-sm text-muted-foreground">通用配置（待实现）</p>
    </div>
  );
}

function LLMSettings() {
  return (
    <div className="p-6 max-w-2xl">
      <h2 className="text-lg font-semibold mb-1">LLM 模型</h2>
      <p className="text-sm text-muted-foreground mb-6">配置 AI 语言模型参数</p>
      {['DeepSeek V4 Flash', 'Claude Sonnet 4.6', 'GPT-4o'].map(name => (
        <div key={name} className="flex items-center justify-between px-3 py-2.5 mb-2 rounded-md bg-secondary">
          <span className="text-sm">{name}</span>
          <label className="relative inline-flex items-center cursor-pointer">
            <input type="checkbox" className="sr-only peer" defaultChecked={name === 'DeepSeek V4 Flash'} />
            <div className="w-8 h-4 rounded-full bg-muted-foreground/30 peer-checked:bg-primary after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:after:translate-x-4" />
          </label>
        </div>
      ))}
    </div>
  );
}

function Placeholder({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="p-6 max-w-2xl">
      <h2 className="text-lg font-semibold mb-1">{title}</h2>
      <p className="text-sm text-muted-foreground mb-6">{desc}</p>
    </div>
  );
}

/* ── Watcher Settings Tab ── */

function WatcherSettings() {
  const [settings, setSettings] = useState<Record<string, any>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [watcherRunning, setWatcherRunning] = useState(false);
  const [watcherDetail, setWatcherDetail] = useState('');
  const [statusLoading, setStatusLoading] = useState(false);

  useEffect(() => {
    fetch('/v1/settings')
      .then(r => r.json())
      .then(d => { setSettings(d); setLoading(false); })
      .catch(() => { showToast('加载设置失败', 'error'); setLoading(false); });
  }, []);

  const loadStatus = () => {
    fetch('/v1/watcher/status')
      .then(r => r.json())
      .then(d => {
        setWatcherRunning(d.running);
        setWatcherDetail(typeof d.detail === 'string' ? d.detail : '');
      })
      .catch(() => {});
  };

  useEffect(() => {
    loadStatus();
    const id = setInterval(loadStatus, 5000);
    return () => clearInterval(id);
  }, []);

  const toggleWatcher = async (start: boolean) => {
    setStatusLoading(true);
    try {
      const r = await fetch(`/v1/watcher/${start ? 'start' : 'stop'}`, { method: 'POST' });
      const d = await r.json();
      setWatcherRunning(d.running);
      loadStatus();
    } catch { showToast('操作失败', 'error'); }
    setStatusLoading(false);
  };

  const save = async () => {
    setSaving(true);
    try {
      const r = await fetch('/v1/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      if (r.ok) showToast('设置已保存', 'success');
      else showToast('保存失败', 'error');
    } catch { showToast('保存请求失败', 'error'); }
    setSaving(false);
  };

  const field = (key: string) => settings[key] ?? '';

  if (loading) return (
    <div className="p-6">
      <Skeleton className="h-5 w-32 mb-2" />
      <Skeleton className="h-4 w-64 mb-6" />
      {[1,2,3,4].map(i => <Skeleton key={i} className="h-10 w-full mb-3" />)}
    </div>
  );

  return (
    <div className="p-6 flex flex-col min-h-0 max-w-2xl">
      <h2 className="text-lg font-semibold mb-1">资料监控</h2>
      <p className="text-sm text-muted-foreground mb-6">配置原始目录监听和自动导入</p>

      {/* Status bar */}
      <section className="mb-6">
        <h3 className="text-sm font-medium mb-2">监听状态</h3>
        <div className="flex items-center justify-between px-3 py-2.5 rounded-md bg-secondary">
          <div className="flex items-center gap-2">
            <span className={`w-2 h-2 rounded-full ${watcherRunning ? 'bg-green-500' : 'bg-muted-foreground'}`} />
            <span className="text-sm">{watcherRunning ? '运行中' : '已停止'}</span>
            {watcherDetail && <span className="text-xs text-muted-foreground ml-1">· {watcherDetail}</span>}
          </div>
          <Button
            size="sm"
            variant={watcherRunning ? 'outline' : 'default'}
            onClick={() => toggleWatcher(!watcherRunning)}
            disabled={statusLoading}
          >
            {watcherRunning ? <Square className="h-3 w-3 mr-1" /> : <Play className="h-3 w-3 mr-1" />}
            {watcherRunning ? '停止' : '启动'}
          </Button>
        </div>
      </section>

      {/* Toggle switches */}
      <section className="mb-6 space-y-3">
        <h3 className="text-sm font-medium mb-2">基本设置</h3>
        {[
          { key: 'watcher_enabled', label: '启用监听', desc: '定时扫描 raw/sources/ 目录文件变化' },
          { key: 'watcher_auto_extract', label: '自动提取', desc: '发现新文件后自动触发 ingest 提取到 Wiki' },
        ].map(({ key, label, desc }) => (
          <div key={key} className="flex items-center justify-between px-3 py-2.5 rounded-md bg-secondary">
            <div>
              <span className="text-sm">{label}</span>
              <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" className="sr-only peer" checked={!!field(key)}
                onChange={e => setSettings(prev => ({ ...prev, [key]: e.target.checked }))} />
              <div className="w-8 h-4 rounded-full bg-muted-foreground/30 peer-checked:bg-primary after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:after:translate-x-4" />
            </label>
          </div>
        ))}
      </section>

      {/* Number inputs */}
      <section className="mb-6 space-y-3">
        <h3 className="text-sm font-medium mb-2">扫描参数</h3>
        {[
          { key: 'watcher_poll_interval', label: '轮询间隔（秒）', type: 'number', min: 1, max: 300 },
          { key: 'watcher_max_file_size_mb', label: '文件大小上限（MB）', type: 'number', min: 1, max: 1024 },
        ].map(({ key, label, type, min, max }) => (
          <div key={key} className="flex items-center justify-between px-3 py-2.5 rounded-md bg-secondary">
            <span className="text-sm">{label}</span>
            <input
              type={type}
              className="w-20 text-right bg-transparent border border-border rounded px-2 py-1 text-sm"
              value={field(key)}
              min={min} max={max}
              onChange={e => setSettings(prev => ({ ...prev, [key]: parseInt(e.target.value) || 0 }))}
            />
          </div>
        ))}
      </section>

      {/* Text inputs */}
      <section className="mb-6 space-y-3">
        <h3 className="text-sm font-medium mb-2">过滤规则</h3>
        {[
          { key: 'watcher_allowed_extensions', label: '允许的后缀', desc: '逗号分隔，如 .md,.txt,.pdf' },
          { key: 'watcher_exclude_folders', label: '排除目录', desc: '逗号分隔，如 .git,node_modules' },
          { key: 'watcher_exclude_extensions', label: '排除后缀', desc: '逗号分隔，如 tmp,bak,exe' },
          { key: 'watcher_exclude_patterns', label: '排除模式', desc: 'fnmatch 模式，逗号分隔' },
        ].map(({ key, label, desc }) => (
          <div key={key} className="px-3 py-2.5 rounded-md bg-secondary">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm">{label}</span>
            </div>
            {desc && <p className="text-xs text-muted-foreground mb-1.5">{desc}</p>}
            <input
              className="w-full bg-transparent border border-border rounded px-2 py-1 text-sm"
              value={field(key)}
              onChange={e => setSettings(prev => ({ ...prev, [key]: e.target.value }))}
            />
          </div>
        ))}
      </section>

      <div className="flex-1" />
      <div className="flex items-center justify-between pt-4 border-t border-border">
        <span className="text-xs text-muted-foreground">改动需要保存后生效</span>
        <Button onClick={save} size="sm" disabled={saving}>
          <Save className="h-3.5 w-3.5 mr-1" />
          {saving ? '保存中...' : '保存'}
        </Button>
      </div>
    </div>
  );
}

/* ── Health Check Tab ── */

interface HealthData {
  status: string; version?: string; uptime_seconds?: number;
  total_pages?: number; graph_nodes?: number; graph_edges?: number;
  ingest_queue_pending?: number;
}

function fmtUptime(s: number): string {
  if (s < 60) return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

interface MetricProps {
  icon: React.ReactNode; label: string; value: string | number;
  sub?: string; variant?: 'default' | 'success' | 'warning' | 'error';
}

function Metric({ icon, label, value, sub, variant = 'default' }: MetricProps) {
  const borderColor = variant === 'success' ? 'border-l-green-500'
    : variant === 'warning' ? 'border-l-amber-500'
    : variant === 'error' ? 'border-l-red-500' : 'border-l-border';
  const iconColor = variant === 'success' ? 'text-green-500'
    : variant === 'warning' ? 'text-amber-500'
    : variant === 'error' ? 'text-red-500' : 'text-muted-foreground';
  return (
    <Card className={`rounded-xl border-l-3 ${borderColor} transition-shadow hover:shadow-md`}>
      <CardContent className="p-4">
        <div className="flex items-start justify-between">
          <div className="space-y-1">
            <p className="text-xs text-muted-foreground">{label}</p>
            <p className="text-2xl font-semibold tracking-tight">{value}</p>
            {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
          </div>
          <div className={`${iconColor} opacity-60`}>{icon}</div>
        </div>
      </CardContent>
    </Card>
  );
}

function HealthSettings() {
  const [data, setData] = useState<HealthData | null>(null);
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');
  const [errMsg, setErrMsg] = useState('');

  useEffect(() => {
    fetch('/health')
      .then(r => r.json())
      .then(d => { setData(d); setStatus(d.status === 'ok' ? 'ok' : 'error'); if (d.status !== 'ok') setErrMsg(d.message || '异常'); })
      .catch(e => { setStatus('error'); setErrMsg(e.message || '无法连接'); });
  }, []);

  return (
    <div className="p-6 overflow-y-auto">
      <h2 className="text-lg font-semibold mb-1">健康检查</h2>
      <p className="text-sm text-muted-foreground mb-6">系统运行状态和关键指标</p>

      {status === 'loading' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1,2,3,4,5,6].map(i => (
            <Card key={i}><CardContent className="p-4 space-y-2"><Skeleton className="h-3 w-20" /><Skeleton className="h-8 w-16" /></CardContent></Card>
          ))}
        </div>
      ) : status === 'error' ? (
        <Card className="border-l-3 border-l-red-500">
          <CardContent className="p-6 flex items-center gap-4">
            <AlertCircle className="h-8 w-8 text-red-500 shrink-0" />
            <div><p className="font-semibold text-destructive">服务异常</p><p className="text-sm text-muted-foreground">{errMsg}</p></div>
          </CardContent>
        </Card>
      ) : (
        <>
          <Card className="mb-6 border-l-3 border-l-green-500 bg-green-500/5">
            <CardContent className="p-4 flex items-center gap-3">
              <CheckCircle2 className="h-5 w-5 text-green-500" />
              <div><p className="text-sm font-medium text-green-600 dark:text-green-400">服务正常</p><p className="text-xs text-muted-foreground">所有系统正常运行</p></div>
            </CardContent>
          </Card>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <Metric icon={<Activity className="h-5 w-5" />} label="运行状态" value={data?.status === 'ok' ? '正常' : '异常'} variant={data?.status === 'ok' ? 'success' : 'error'} />
            <Metric icon={<Package className="h-5 w-5" />} label="服务版本" value={data?.version || '-'} />
            <Metric icon={<Timer className="h-5 w-5" />} label="运行时间" value={data?.uptime_seconds != null ? fmtUptime(data.uptime_seconds) : '-'} />
            <Metric icon={<FileText className="h-5 w-5" />} label="Wiki 页面数" value={data?.total_pages ?? '-'} />
            <Metric icon={<NetworkIcon className="h-5 w-5" />} label="图谱节点" value={data?.graph_nodes ?? '-'} sub={data?.graph_edges != null ? `${data.graph_edges} 条连接` : undefined} />
            <Metric icon={<ListTodo className="h-5 w-5" />} label="导入队列待处理" value={data?.ingest_queue_pending ?? '-'} variant={data?.ingest_queue_pending && data.ingest_queue_pending > 0 ? 'warning' : 'success'} sub={data?.ingest_queue_pending && data.ingest_queue_pending > 0 ? '等待处理中' : '队列为空'} />
          </div>
          <details className="mt-6">
            <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">原始响应数据</summary>
            <pre className="mt-2 text-xs bg-muted p-3 rounded-md overflow-x-auto border">{JSON.stringify(data, null, 2)}</pre>
          </details>
        </>
      )}
    </div>
  );
}
