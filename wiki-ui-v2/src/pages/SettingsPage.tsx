import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Sun, Moon, Monitor, Minus, Plus, Save, Palette, SlidersHorizontal, Brain,
  Eye, Activity, Shield, Lock, Target, Trash2, Plus as PlusIcon, Key,
  AlertCircle, CheckCircle2, Loader2, EyeOff, RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { showToast } from '@/components/shared/Toast';
import { useTheme } from '@/hooks/useTheme';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Package, Timer, FileText, Network as NetworkIcon, ListTodo } from 'lucide-react';
import { fetchJson, postJson, putJson, deleteJson } from '@/api/client';

/* ──────────────────────────────────────────────
   Tabs 定义（去掉空壳 embedding / network）
   ────────────────────────────────────────────── */

const settingsTabs = [
  { key: 'interface', label: '界面', icon: Palette },
  { key: 'general', label: '通用', icon: SlidersHorizontal },
  { key: 'llm', label: 'LLM 模型', icon: Brain },
  { key: 'watcher', label: '资料监控', icon: Eye },
  { key: 'privacy', label: '隐私', icon: Shield },
  { key: 'security', label: '安全', icon: Lock },
  { key: 'purpose', label: '知识库目标', icon: Target },
  { key: 'health', label: '健康检查', icon: Activity },
];

const PROVIDER_OPTIONS = [
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'doubao', label: '豆包（火山引擎）' },
];

const MODEL_OPTIONS: Record<string, string[]> = {
  deepseek: ['deepseek-v4-flash', 'deepseek-v4-pro', 'deepseek-chat'],
  doubao: ['ep-20260704205018-srlpk'],
};

const SEARCH_METHODS = [
  { value: 'bm25', label: 'BM25 关键词', desc: '快，适合精确词匹配' },
  { value: 'vector', label: '向量语义', desc: '懂语义，需 embedding' },
  { value: 'hybrid', label: '混合检索', desc: 'RRF 融合（推荐）' },
];

const LANGUAGES = [
  { value: 'zh', label: '中文' },
  { value: 'en', label: 'English' },
];

export default function SettingsPage() {
  const { tab: activeTab } = useParams<{ tab: string }>();
  const navigate = useNavigate();
  const tab = activeTab || 'interface';

  // 提升 useBackendSettings 到父组件，所有 BackendSettings tab 共享
  const { settings, setSettings, loading, saving, save } = useBackendSettings();
  const [originalSnapshot, setOriginalSnapshot] = useState<string | null>(null);
  const [savedFeedback, setSavedFeedback] = useState(false);
  const savedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 首次加载时保存初始快照用于脏检测
  useEffect(() => {
    if (settings && originalSnapshot === null) {
      setOriginalSnapshot(JSON.stringify(settings));
    }
  }, [settings, originalSnapshot]);

  const dirty = originalSnapshot !== null && settings !== null
    && originalSnapshot !== JSON.stringify(settings);

  const handleSave = async () => {
    if (!dirty || saving) return;
    const saved = await save();
    // 用服务端返回值更新快照（避免本地序列化差异导致的误判）
    if (saved) setOriginalSnapshot(JSON.stringify(saved));
    setSavedFeedback(true);
    if (savedTimer.current) clearTimeout(savedTimer.current);
    savedTimer.current = setTimeout(() => setSavedFeedback(false), 2000);
  };

  // Ctrl+S / Cmd+S 快捷键保存
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [dirty, saving]);

  const uiSettings = {
    theme: settings?.theme ?? 'light',
  };

  const updateSettings = (patch: Partial<BackendSettings>) =>
    setSettings(prev => prev ? { ...prev, ...patch } : prev);

  /* ------------------------------------------------------------------ */
  /*  统一保存栏 — sticky 底部                                          */
  /* ------------------------------------------------------------------ */

  function SettingsSaveBar() {
    return (
      <div className="sticky bottom-0 left-0 right-0 border-t border-border/60 bg-card/95 backdrop-blur-md px-6 py-3 flex items-center justify-between z-10 shadow-[0_-4px_16px_-8px_rgba(0,0,0,0.12)] dark:shadow-[0_-4px_16px_-8px_rgba(0,0,0,0.5)]">
        <div className="flex items-center gap-2 h-8">
          {dirty && !saving && (
            <span className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-400">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              有未保存的改动
              <kbd className="ml-1 text-[10px] px-1 py-0.5 rounded border border-border bg-muted text-muted-foreground">Ctrl+S</kbd>
            </span>
          )}
          {saving && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              正在保存...
            </span>
          )}
          {savedFeedback && !dirty && (
            <span className="flex items-center gap-1.5 text-xs text-green-600 dark:text-green-400 animate-in fade-in">
              <CheckCircle2 className="h-3.5 w-3.5" />
              已保存到数据库
            </span>
          )}
          {!dirty && !saving && !savedFeedback && (
            <span className="text-xs text-muted-foreground">所有改动已保存</span>
          )}
        </div>
        <Button
          onClick={handleSave}
          disabled={!dirty || saving}
          size="sm"
          className={`
            min-w-[120px] transition-all duration-300
            ${dirty
              ? 'shadow-md shadow-primary/25 hover:shadow-lg hover:shadow-primary/35 hover:-translate-y-0.5 active:translate-y-0'
              : 'opacity-50 cursor-not-allowed'
            }
          `}
        >
          {saving ? (
            <span className="flex items-center gap-1.5">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              保存中...
            </span>
          ) : (
            <span className="flex items-center gap-1.5">
              <Save className="h-3.5 w-3.5" />
              保存设置
            </span>
          )}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-1 min-h-0">
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

      {loading ? (
        <div className="flex-1 overflow-y-auto p-6"><LoadingSkeleton /></div>
      ) : (
        <div className="flex-1 flex flex-col min-h-0 relative">
          <div className="flex-1 overflow-y-auto">
            {tab === 'interface' && (
              <InterfaceSettings
                theme={uiSettings.theme}
                onThemeChange={v => updateSettings({ theme: v })}
              />
            )}
            {tab === 'general' && (
              <GeneralSettings
                settings={settings!}
                setSettings={updateSettings}
              />
            )}
            {tab === 'llm' && (
              <LLMSettings
                settings={settings!}
                setSettings={updateSettings}
              />
            )}
            {tab === 'watcher' && (
              <WatcherSettings
                settings={settings!}
                setSettings={updateSettings}
              />
            )}
            {tab === 'privacy' && (
              <PrivacySettings
                settings={settings!}
                setSettings={updateSettings}
              />
            )}
            {tab === 'security' && <SecuritySettings />}
            {tab === 'purpose' && <PurposeSettings />}
            {tab === 'health' && <HealthSettings />}
            <div className="h-4" /> {/* 底部间距 */}
          </div>
          <SettingsSaveBar />
        </div>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────
   通用 Toggle Switch（无 shadcn switch 组件，内建）
   ────────────────────────────────────────────── */

function Switch({ checked, onChange, disabled }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean }) {
  return (
    <label className={`relative inline-flex items-center cursor-pointer ${disabled ? 'opacity-50' : ''}`}>
      <input
        type="checkbox"
        className="sr-only peer"
        checked={checked}
        disabled={disabled}
        onChange={e => onChange(e.target.checked)}
      />
      <div className="w-9 h-5 rounded-full bg-muted-foreground/30 peer-checked:bg-primary after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-4" />
    </label>
  );
}

/* ──────────────────────────────────────────────
   通用「设置行」布局
   ────────────────────────────────────────────── */

function SettingRow({ label, desc, children }: { label: string; desc?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3 rounded-md bg-secondary/60">
      <div className="min-w-0 flex-1">
        <span className="text-sm font-medium">{label}</span>
        {desc && <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

function SectionHeader({ title, desc }: { title: string; desc?: string }) {
  return (
    <div className="mb-3 mt-6 first:mt-0">
      <h3 className="text-sm font-semibold">{title}</h3>
      {desc && <p className="text-xs text-muted-foreground mt-0.5">{desc}</p>}
    </div>
  );
}

/* ──────────────────────────────────────────────
   1. 界面（主题存入后端 settings；缩放本地 localStorage 即时生效）
   ────────────────────────────────────────────── */

interface InterfaceProps {
  theme: string;
  onThemeChange: (v: string) => void;
}

function InterfaceSettings({ theme, onThemeChange }: InterfaceProps) {
  const { setTheme } = useTheme();
  const [zoom, setZoom] = useState(() => parseInt(localStorage.getItem('ui_zoom') || '100'));

  useEffect(() => {
    const clamped = Math.max(50, Math.min(200, zoom));
    document.documentElement.style.fontSize = `${clamped}%`;
  }, [zoom]);

  useEffect(() => {
    // 保存缩放（本地即时生效，不经过后端保存栏）
    localStorage.setItem('ui_zoom', String(Math.max(50, Math.min(200, zoom))));
  }, [zoom]);

  const handleTheme = (v: string) => {
    setTheme(v as 'light' | 'dark' | 'system');
    onThemeChange(v);
  };

  return (
    <div className="p-6 flex flex-col min-h-0 max-w-2xl">
      <h2 className="text-lg font-semibold mb-1">界面</h2>
      <p className="text-sm text-muted-foreground mb-6">主题外观与界面缩放</p>

      <SectionHeader title="主题" desc="点击「保存设置」后持久化，切换即时预览" />
      <div className="flex gap-2 mb-4">
        {[
          { value: 'light', label: '浅色', icon: Sun },
          { value: 'dark', label: '深色', icon: Moon },
          { value: 'system', label: '跟随系统', icon: Monitor },
        ].map(opt => (
          <button
            key={opt.value}
            className={`flex items-center gap-1.5 px-4 py-2 text-sm rounded-md cursor-pointer transition-all duration-200 ${
              theme === opt.value
                ? 'bg-primary text-primary-foreground shadow-sm shadow-primary/20'
                : 'border border-border bg-secondary text-secondary-foreground hover:bg-accent hover:-translate-y-0.5'
            }`}
            onClick={() => handleTheme(opt.value)}
          >
            <opt.icon className="h-4 w-4" />
            {opt.label}
          </button>
        ))}
      </div>

      <SectionHeader title="界面缩放" desc="调整全局字体大小（50%–200%），即时生效，自动保存到本地" />
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
    </div>
  );
}

/* ──────────────────────────────────────────────
   2. 通用（对接后端 output_language / search_method）
   ────────────────────────────────────────────── */

interface BackendSettings {
  llm_provider: string;
  deepseek_api_key: string;
  deepseek_model: string;
  output_language: string;
  search_method: string;
  theme: string;
  privacy_enabled: boolean;
  watcher_enabled: boolean;
  watcher_auto_extract: boolean;
  watcher_poll_interval: number;
  watcher_max_file_size_mb: number;
  watcher_allowed_extensions: string;
  watcher_exclude_folders: string;
  watcher_exclude_extensions: string;
  watcher_exclude_patterns: string;
}

function useBackendSettings() {
  const [settings, setSettings] = useState<BackendSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    fetchJson<BackendSettings>('/v1/settings')
      .then(d => { setSettings(d); setLoading(false); })
      .catch(() => { showToast('加载设置失败', 'error'); setLoading(false); });
  }, []);

  useEffect(() => { load(); }, [load]);

  // 返回保存后的数据（不弹 toast — 由父级 SaveBar 统一反馈）
  const save = useCallback(async (): Promise<BackendSettings | null> => {
    if (!settings) return null;
    setSaving(true);
    try {
      const saved = await postJson<BackendSettings>('/v1/settings', settings);
      setSettings(saved);
      setSaving(false);
      return saved;
    } catch (e) {
      setSaving(false);
      showToast('保存失败，请检查网络', 'error');
      return null;
    }
  }, [settings]);

  return { settings, setSettings, loading, saving, save, reload: load };
}

function LoadingSkeleton() {
  return (
    <div className="p-6">
      <Skeleton className="h-5 w-32 mb-2" />
      <Skeleton className="h-4 w-64 mb-6" />
      {[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-12 w-full mb-3" />)}
    </div>
  );
}

interface BackendTabProps {
  settings: BackendSettings;
  setSettings: (patch: Partial<BackendSettings>) => void;
}

function GeneralSettings({ settings, setSettings }: BackendTabProps) {
  const update = (patch: Partial<BackendSettings>) => setSettings(patch);

  return (
    <div className="p-6 flex flex-col min-h-0 max-w-2xl">
      <h2 className="text-lg font-semibold mb-1">通用设置</h2>
      <p className="text-sm text-muted-foreground mb-6">输出语言和搜索方式（服务端持久化）</p>

      <SectionHeader title="输出语言" desc="LLM 生成 Wiki 内容的默认语言" />
      <div className="flex gap-2 mb-4">
        {LANGUAGES.map(opt => (
          <button
            key={opt.value}
            className={`px-4 py-2 text-sm rounded-md cursor-pointer transition-all duration-200 ${
              settings.output_language === opt.value
                ? 'bg-primary text-primary-foreground shadow-sm shadow-primary/20'
                : 'border border-border bg-secondary text-secondary-foreground hover:bg-accent hover:-translate-y-0.5'
            }`}
            onClick={() => update({ output_language: opt.value })}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <SectionHeader title="搜索方式" desc="默认检索算法（可在检索页临时切换）" />
      <div className="space-y-2 mb-4">
        {SEARCH_METHODS.map(m => (
          <button
            key={m.value}
            className={`w-full text-left px-4 py-3 rounded-md cursor-pointer transition-all duration-200 border ${
              settings.search_method === m.value
                ? 'bg-primary/10 border-primary text-foreground shadow-sm'
                : 'bg-secondary/60 border-transparent hover:bg-accent hover:-translate-y-0.5 text-secondary-foreground'
            }`}
            onClick={() => update({ search_method: m.value })}
          >
            <div className="text-sm font-medium">{m.label}</div>
            <div className="text-xs text-muted-foreground mt-0.5">{m.desc}</div>
          </button>
        ))}
      </div>

    </div>
  );
}

/* ------------------------------------------------
   3. LLM Model (llm_provider / api_key / model)
   ------------------------------------------------ */

function LLMSettings({ settings, setSettings }: BackendTabProps) {
  const [showKey, setShowKey] = useState(false);

  const update = (patch: Partial<BackendSettings>) => setSettings(patch);
  const models = MODEL_OPTIONS[settings.llm_provider] || [];

  return (
    <div className="p-6 flex flex-col min-h-0 max-w-2xl">
      <h2 className="text-lg font-semibold mb-1">LLM 模型</h2>
      <p className="text-sm text-muted-foreground mb-6">配置 AI 模型 Provider 和密钥</p>

      <SectionHeader title="服务提供商" />
      <div className="flex gap-2 mb-4 flex-wrap">
        {PROVIDER_OPTIONS.map(opt => (
          <button
            key={opt.value}
            className={`px-4 py-2 text-sm rounded-md cursor-pointer transition-all duration-200 ${
              settings.llm_provider === opt.value
                ? 'bg-primary text-primary-foreground shadow-sm shadow-primary/20'
                : 'border border-border bg-secondary text-secondary-foreground hover:bg-accent hover:-translate-y-0.5'
            }`}
            onClick={() => {
              const defModel = PROVIDER_CONFIG_DEFAULTS[opt.value] || '';
              update({ llm_provider: opt.value, deepseek_model: defModel });
            }}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <SectionHeader title="API 密钥" desc="密钥保存在本地数据库，不经过第三方" />
      <div className="relative mb-4">
        <Input
          type={showKey ? 'text' : 'password'}
          value={settings.deepseek_api_key}
          onChange={e => update({ deepseek_api_key: e.target.value })}
          placeholder="sk-..."
          className="pr-10 font-mono text-sm focus-visible:ring-primary/30"
        />
        <button
          className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors p-1 rounded"
          onClick={() => setShowKey(!showKey)}
          title={showKey ? '隐藏密钥' : '显示密钥'}
        >
          {showKey ? <EyeOff className="h-4 w-4" /> : <Key className="h-4 w-4" />}
        </button>
      </div>

      <SectionHeader title="模型" desc="选择该 Provider 下使用的具体模型" />
      <div className="flex gap-2 mb-4 flex-wrap">
        {models.map(m => (
          <button
            key={m}
            className={`px-3 py-1.5 text-xs font-mono rounded-md cursor-pointer transition-all duration-200 ${
              settings.deepseek_model === m
                ? 'bg-primary text-primary-foreground shadow-sm shadow-primary/20'
                : 'border border-border bg-secondary text-secondary-foreground hover:bg-accent hover:-translate-y-0.5'
            }`}
            onClick={() => update({ deepseek_model: m })}
          >
            {m}
          </button>
        ))}
      </div>

      <div className="mt-2 px-4 py-3 rounded-md bg-amber-500/10 border border-amber-500/20">
        <p className="text-xs text-amber-700 dark:text-amber-400">
          ⚠️ 更改 Provider/模型后，需要重启后端服务才能完全生效。API 密钥热生效。
        </p>
      </div>
    </div>
  );
}

const PROVIDER_CONFIG_DEFAULTS: Record<string, string> = {
  deepseek: 'deepseek-v4-flash',
  doubao: 'ep-20260704205018-srlpk',
};

/* ──────────────────────────────────────────────
   4. 资料监控
   ────────────────────────────────────────────── */

function WatcherSettings({ settings, setSettings }: BackendTabProps) {
  const [watcherRunning, setWatcherRunning] = useState(false);
  const [watcherDetail, setWatcherDetail] = useState('');
  const [statusLoading, setStatusLoading] = useState(false);

  const loadStatus = () => {
    fetchJson<{ running: boolean; detail?: string }>('/v1/watcher/status')
      .then(d => { setWatcherRunning(d.running); setWatcherDetail(typeof d.detail === 'string' ? d.detail : ''); })
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
      const d = await postJson<{ running: boolean; detail?: string }>(`/v1/watcher/${start ? 'start' : 'stop'}`);
      setWatcherRunning(d.running);
      loadStatus();
    } catch { showToast('操作失败', 'error'); }
    setStatusLoading(false);
  };

  const update = (patch: Partial<BackendSettings>) => setSettings(patch);

  return (
    <div className="p-6 flex flex-col min-h-0 max-w-2xl">
      <h2 className="text-lg font-semibold mb-1">资料监控</h2>
      <p className="text-sm text-muted-foreground mb-6">配置 raw/sources/ 目录监听和自动导入</p>

      <SectionHeader title="监听状态" />
      <div className="flex items-center justify-between px-4 py-3 rounded-md bg-secondary/60 mb-6">
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
          {watcherRunning ? '停止' : '启动'}
        </Button>
      </div>

      <SectionHeader title="基本设置" />
      <div className="space-y-2 mb-4">
        <SettingRow label="启用监听" desc="定时扫描 raw/sources/ 目录文件变化">
          <Switch checked={settings.watcher_enabled} onChange={v => update({ watcher_enabled: v })} />
        </SettingRow>
        <SettingRow label="自动提取" desc="发现新文件后自动触发 ingest 提取到 Wiki">
          <Switch checked={settings.watcher_auto_extract} onChange={v => update({ watcher_auto_extract: v })} />
        </SettingRow>
      </div>

      <SectionHeader title="扫描参数" />
      <div className="space-y-2 mb-4">
        {[
          { key: 'watcher_poll_interval' as const, label: '轮询间隔（秒）', min: 1, max: 300 },
          { key: 'watcher_max_file_size_mb' as const, label: '文件大小上限（MB）', min: 1, max: 1024 },
        ].map(({ key, label, min, max }) => (
          <div key={key} className="flex items-center justify-between gap-4 px-4 py-3 rounded-md bg-secondary/60">
            <span className="text-sm">{label}</span>
            <input
              type="number"
              className="w-20 text-right bg-transparent border border-border rounded px-2 py-1 text-sm"
              value={settings[key]}
              min={min} max={max}
              onChange={e => update({ [key]: parseInt(e.target.value) || 0 })}
            />
          </div>
        ))}
      </div>

      <SectionHeader title="过滤规则" desc="逗号分隔，控制哪些文件会被处理" />
      <div className="space-y-3 mb-4">
        {[
          { key: 'watcher_allowed_extensions' as const, label: '允许的后缀', desc: '如 .md,.txt,.pdf' },
          { key: 'watcher_exclude_folders' as const, label: '排除目录', desc: '如 .git,node_modules' },
          { key: 'watcher_exclude_extensions' as const, label: '排除后缀', desc: '如 tmp,bak,exe' },
          { key: 'watcher_exclude_patterns' as const, label: '排除模式', desc: 'fnmatch glob 模式' },
        ].map(({ key, label, desc }) => (
          <div key={key} className="px-4 py-3 rounded-md bg-secondary/60">
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium">{label}</span>
            </div>
            <p className="text-xs text-muted-foreground mb-1.5">{desc}</p>
            <Input
              className="text-sm font-mono"
              value={settings[key]}
              onChange={e => update({ [key]: e.target.value })}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

/* ──────────────────────────────────────────────
   5. 隐私规则（对接 /v1/privacy/rules）
   ────────────────────────────────────────────── */

interface PrivacyRule { keyword: string; category: string; is_default?: boolean }
interface PrivacyRulesResponse { rules: PrivacyRule[] }

const CATEGORY_LABELS: Record<string, string> = {
  emotion: '情感与关系',
  financial: '财务',
  identity: '个人身份',
  health: '健康',
  general: '通用',
};

const CATEGORY_COLORS: Record<string, string> = {
  emotion: 'bg-pink-500/15 text-pink-600 dark:text-pink-400 border-pink-500/20',
  financial: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/20',
  identity: 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/20',
  health: 'bg-green-500/15 text-green-600 dark:text-green-400 border-green-500/20',
  general: 'bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/20',
};

function PrivacySettings({ settings, setSettings }: BackendTabProps) {
  const [rules, setRules] = useState<PrivacyRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [newKeyword, setNewKeyword] = useState('');
  const [newCategory, setNewCategory] = useState('general');
  const [adding, setAdding] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(() => {
    fetchJson<PrivacyRulesResponse>('/v1/privacy/rules')
      .then(d => { setRules(d.rules || []); setLoading(false); })
      .catch(() => { showToast('加载隐私规则失败', 'error'); setLoading(false); });
  }, []);

  useEffect(() => { load(); }, [load]);

  const privacyEnabled = settings?.privacy_enabled ?? false;

  const addRule = async () => {
    const kw = newKeyword.trim();
    if (!kw) return;
    setAdding(true);
    try {
      await postJson<PrivacyRule>('/v1/privacy/rules', { keyword: kw, category: newCategory });
      setNewKeyword('');
      load();
      showToast(`已添加规则：${kw}`, 'success');
    } catch { showToast('添加失败', 'error'); }
    setAdding(false);
  };

  const deleteRule = async (keyword: string) => {
    setDeleting(keyword);
    try {
      await deleteJson(`/v1/privacy/rules/${encodeURIComponent(keyword)}`);
      load();
      showToast(`已删除：${keyword}`, 'success');
    } catch { showToast('删除失败', 'error'); }
    setDeleting(null);
  };

  // 按分类分组
  const grouped = Object.keys(CATEGORY_LABELS).map(cat => ({
    key: cat,
    label: CATEGORY_LABELS[cat],
    items: rules.filter(r => r.category === cat),
  }));

  return (
    <div className="p-6 flex flex-col min-h-0 max-w-3xl">
      <h2 className="text-lg font-semibold mb-1">隐私规则</h2>
      <p className="text-sm text-muted-foreground mb-6">
        配置敏感关键词，命中后 LLM 会在生成内容时自动过滤这些信息
      </p>

      {/* 总开关 — privacy_enabled */}
      <SettingRow
        label="隐私过滤"
        desc={privacyEnabled ? '已启用：导入资料时检测敏感内容并标记为受限' : '已关闭：隐私检测不生效，所有资料正常导入'}
      >
        <div className="flex items-center gap-2">
          <span className={`text-xs ${privacyEnabled ? 'text-primary font-medium' : 'text-muted-foreground'}`}>
            {privacyEnabled ? '已启用' : '已关闭'}
          </span>
          <Switch
            checked={privacyEnabled}
            onChange={v => setSettings({ privacy_enabled: v })}
          />
        </div>
      </SettingRow>

      <div className="border-t border-border/40 my-4" />

      {/* 添加新规则 */}
      <div className={`flex gap-2 mb-6 transition-opacity ${privacyEnabled ? '' : 'opacity-50 pointer-events-none'}`}>
        <Input
          placeholder="输入敏感关键词..."
          value={newKeyword}
          onChange={e => setNewKeyword(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') addRule(); }}
          className="flex-1"
        />
        <select
          className="px-3 py-1.5 text-sm rounded-md border border-border bg-secondary text-secondary-foreground"
          value={newCategory}
          onChange={e => setNewCategory(e.target.value)}
        >
          {Object.entries(CATEGORY_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <Button onClick={addRule} disabled={adding || !newKeyword.trim()} size="sm">
          {adding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlusIcon className="h-3.5 w-3.5" />}
        </Button>
      </div>

      {loading ? (
        <div className="space-y-3">{[1, 2, 3, 4].map(i => <Skeleton key={i} className="h-20 w-full" />)}</div>
      ) : (
        <div className={`space-y-5 transition-opacity ${privacyEnabled ? '' : 'opacity-50'}`}>
          {!privacyEnabled && (
            <div className="text-xs text-muted-foreground px-1 py-2 rounded-md bg-muted/50 border border-border">
              💤 隐私过滤已关闭，规则列表只读展示，开启后生效
            </div>
          )}
          {grouped.map(({ key, label, items }) => (
            <div key={key}>
              <div className="flex items-center gap-2 mb-2">
                <h3 className="text-sm font-semibold">{label}</h3>
                <Badge variant="outline" className="text-xs">{items.length}</Badge>
              </div>
              {items.length === 0 ? (
                <p className="text-xs text-muted-foreground px-1">暂无规则</p>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {items.map(r => (
                    <div
                      key={r.keyword}
                      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md border text-xs ${CATEGORY_COLORS[r.category] || CATEGORY_COLORS.general}`}
                    >
                      <span>{r.keyword}</span>
                      {!r.is_default && privacyEnabled && (
                        <button
                          className="ml-1 opacity-60 hover:opacity-100 transition-opacity cursor-pointer"
                          onClick={() => deleteRule(r.keyword)}
                          disabled={deleting === r.keyword}
                        >
                          {deleting === r.keyword
                            ? <Loader2 className="h-3 w-3 animate-spin" />
                            : <Trash2 className="h-3 w-3" />}
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <p className="text-xs text-muted-foreground mt-6">
        💡 默认规则（不带删除按钮）不可删除，自定义规则可自由增删
      </p>
    </div>
  );
}

/* ──────────────────────────────────────────────
   6. 安全（密码保护，对接 /v1/auth/*）
   ────────────────────────────────────────────── */

interface AuthStatus { protected: boolean; active_tokens: number }

function SecuritySettings() {
  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [password, setPassword] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);

  const load = useCallback(() => {
    fetchJson<AuthStatus>('/v1/auth/status')
      .then(d => { setStatus(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const setPwd = async () => {
    if (password.length < 4) { showToast('密码至少 4 位', 'error'); return; }
    if (password !== confirmPwd) { showToast('两次密码不一致', 'error'); return; }
    setSaving(true);
    try {
      await postJson('/v1/auth/password', { password });
      showToast('密码已设置', 'success');
      setPassword(''); setConfirmPwd('');
      load();
    } catch { showToast('设置失败', 'error'); }
    setSaving(false);
  };

  const clearPwd = async () => {
    setClearing(true);
    try {
      await postJson('/v1/auth/clear');
      showToast('密码已清除', 'success');
      load();
    } catch { showToast('清除失败', 'error'); }
    setClearing(false);
  };

  if (loading) return <LoadingSkeleton />;

  return (
    <div className="p-6 flex flex-col min-h-0 max-w-2xl">
      <h2 className="text-lg font-semibold mb-1">安全设置</h2>
      <p className="text-sm text-muted-foreground mb-6">Wiki 访问密码保护</p>

      {/* 当前状态 */}
      <div className="mb-6">
        <Card className={`border-l-3 ${status?.protected ? 'border-l-amber-500' : 'border-l-green-500'}`}>
          <CardContent className="p-4 flex items-center gap-3">
            {status?.protected
              ? <Lock className="h-5 w-5 text-amber-500 shrink-0" />
              : <UnlockIcon className="h-5 w-5 text-green-500 shrink-0" />}
            <div>
              <p className="text-sm font-medium">
                {status?.protected ? '密码保护已启用' : '公开访问'}
              </p>
              <p className="text-xs text-muted-foreground">
                {status?.protected
                  ? `当前有 ${status.active_tokens} 个活跃访问 token`
                  : '任何人无需密码即可访问'}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {status?.protected && (
        <div className="mb-6">
          <Button variant="outline" size="sm" onClick={clearPwd} disabled={clearing}>
            {clearing ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : null}
            关闭密码保护
          </Button>
        </div>
      )}

      <SectionHeader title={status?.protected ? '修改密码' : '设置密码'} desc="至少 4 位字符" />
      <div className="space-y-3">
        <Input
          type="password"
          placeholder="新密码"
          value={password}
          onChange={e => setPassword(e.target.value)}
        />
        <Input
          type="password"
          placeholder="确认密码"
          value={confirmPwd}
          onChange={e => setConfirmPwd(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') setPwd(); }}
        />
        <Button onClick={setPwd} disabled={saving || !password} size="sm">
          {saving ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />}
          {saving ? '保存中...' : '保存密码'}
        </Button>
      </div>
    </div>
  );
}

function UnlockIcon({ className }: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={className}>
      <rect width="18" height="11" x="3" y="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/>
    </svg>
  );
}

/* ──────────────────────────────────────────────
   7. 知识库目标（对接 /v1/purpose/*）
   ────────────────────────────────────────────── */

interface DirectionsMap {
  directions: Record<string, { label: string; description: string; hint: string }>;
}

interface PurposeResponse { content: string; exists: boolean }

const PURPOSE_DIR_ICONS: Record<string, string> = {
  reading_notes: '📖',
  meeting_minutes: '📋',
  personal_growth: '🌱',
  tech_docs: '💻',
  academic: '🎓',
  project_management: '📊',
};

function PurposeSettings() {
  const [directions, setDirections] = useState<DirectionsMap['directions']>({});
  const [purpose, setPurpose] = useState<PurposeResponse | null>(null);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    Promise.all([
      fetchJson<DirectionsMap>('/v1/purpose/directions'),
      fetchJson<PurposeResponse>('/v1/purpose'),
    ]).then(([d, p]) => {
      setDirections(d.directions);
      setPurpose(p);
      setEditContent(p.content);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  const generate = async (dir: string) => {
    setGenerating(dir);
    try {
      const p = await postJson<PurposeResponse>('/v1/purpose/generate', { direction: dir });
      setPurpose(p);
      setEditContent(p.content);
      showToast('purpose.md 已生成', 'success');
    } catch { showToast('生成失败', 'error'); }
    setGenerating(null);
  };

  const save = async () => {
    setSaving(true);
    try {
      const p = await putJson<PurposeResponse>('/v1/purpose', { content: editContent });
      setPurpose(p);
      setEditing(false);
      showToast('purpose.md 已保存', 'success');
    } catch { showToast('保存失败', 'error'); }
    setSaving(false);
  };

  if (loading) return <LoadingSkeleton />;

  return (
    <div className="p-6 flex flex-col min-h-0 max-w-3xl">
      <h2 className="text-lg font-semibold mb-1">知识库目标</h2>
      <p className="text-sm text-muted-foreground mb-6">
        定义 Wiki 的核心定位和关注方向（purpose.md）
      </p>

      {/* 从模板生成 */}
      <SectionHeader title="从模板生成" desc="选择方向快速生成 purpose.md" />
      <div className="grid grid-cols-2 gap-2 mb-6">
        {Object.entries(directions).map(([key, info]) => (
          <button
            key={key}
            className="text-left px-4 py-3 rounded-md border border-border bg-secondary/40 hover:bg-accent transition-colors cursor-pointer"
            onClick={() => generate(key)}
            disabled={generating !== null}
          >
            <div className="flex items-center gap-2">
              <span className="text-lg">{PURPOSE_DIR_ICONS[key] || '📄'}</span>
              <span className="text-sm font-medium">{info.label}</span>
              {generating === key && <Loader2 className="h-3 w-3 animate-spin ml-auto" />}
            </div>
            <p className="text-xs text-muted-foreground mt-1">{info.description}</p>
          </button>
        ))}
      </div>

      {/* 当前内容 */}
      <SectionHeader title="当前 purpose.md" />
      {purpose?.exists && !editing ? (
        <div className="rounded-md border border-border bg-secondary/40 p-4 mb-4">
          <pre className="text-sm whitespace-pre-wrap font-sans leading-relaxed">{purpose.content}</pre>
          <div className="mt-3 flex gap-2">
            <Button variant="outline" size="sm" onClick={() => { setEditContent(purpose.content); setEditing(true); }}>
              编辑
            </Button>
          </div>
        </div>
      ) : editing ? (
        <div className="space-y-3 mb-4">
          <Textarea
            value={editContent}
            onChange={e => setEditContent(e.target.value)}
            className="min-h-[200px] font-mono text-sm"
          />
          <div className="flex gap-2">
            <Button onClick={save} disabled={saving} size="sm">
              {saving ? <Loader2 className="h-3.5 w-3.5 mr-1 animate-spin" /> : <Save className="h-3.5 w-3.5 mr-1" />}
              保存
            </Button>
            <Button variant="outline" size="sm" onClick={() => { setEditing(false); setEditContent(purpose?.content || ''); }}>
              取消
            </Button>
          </div>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground mb-4">尚未创建 purpose.md，请从上方选择一个方向生成。</p>
      )}
    </div>
  );
}

/* ──────────────────────────────────────────────
   8. 健康检查（已有 10s 轮询 + 手动刷新）
   ────────────────────────────────────────────── */

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
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const fetchHealth = useCallback(async (showError = false) => {
    try {
      const d = await fetchJson<HealthData>('/health');
      setData(d);
      setStatus(d.status === 'ok' ? 'ok' : 'error');
      if (d.status !== 'ok') setErrMsg(d.version || '异常');
      setLastUpdated(new Date());
    } catch (e: any) {
      if (showError) { setStatus('error'); setErrMsg(e.message || '无法连接'); }
    }
  }, []);

  useEffect(() => {
    fetchHealth(true);
    const id = setInterval(() => fetchHealth(false), 10_000);
    return () => clearInterval(id);
  }, [fetchHealth]);

  const manualRefresh = async () => {
    setRefreshing(true);
    await fetchHealth(true);
    setRefreshing(false);
  };

  return (
    <div className="p-6 overflow-y-auto">
      <div className="flex items-center justify-between mb-1">
        <h2 className="text-lg font-semibold">健康检查</h2>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-muted-foreground">
              上次更新 {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <Button variant="ghost" size="sm" onClick={manualRefresh} disabled={refreshing}>
            <RefreshCw className={`h-3.5 w-3.5 mr-1 ${refreshing ? 'animate-spin' : ''}`} />
            刷新
          </Button>
        </div>
      </div>
      <p className="text-sm text-muted-foreground mb-6">系统运行状态和关键指标（每 10 秒自动刷新）</p>

      {status === 'loading' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3, 4, 5, 6].map(i => (
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
