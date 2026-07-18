import { useState, useEffect } from 'react';
import { useTheme } from '@heroui/react';

const settingsTabs = [
  { key: 'general', label: '通用' },
  { key: 'interface', label: '界面' },
  { key: 'llm', label: 'LLM 模型' },
  { key: 'embedding', label: '向量嵌入' },
  { key: 'network', label: '网络' },
];

export default function SettingsPage() {
  const [tab, setTab] = useState('interface');

  const renderContent = () => {
    switch (tab) {
      case 'interface': return <InterfaceSettings />;
      case 'general': return <GeneralSettings />;
      case 'llm': return <LLMSettings />;
      case 'embedding': return <div style={{color:'var(--muted)',fontSize: "var(--fs-sm)"}}>向量嵌入配置（待实现）</div>;
      case 'network': return <div style={{color:'var(--muted)',fontSize: "var(--fs-sm)"}}>网络配置（待实现）</div>;
    }
  };

  return (
    <div className="flex flex-1 min-h-0">
      <div style={{ width: 220, background: 'var(--surface)', borderRight: '1px solid var(--border)', padding: '8px 0' }}>
        {settingsTabs.map(t => (
          <div key={t.key}
            className="flex items-center px-4 py-2 text-sm cursor-pointer"
            style={{ color: tab === t.key ? 'var(--foreground)' : 'var(--muted)', background: tab === t.key ? 'var(--surface-tertiary)' : 'transparent', borderLeft: tab === t.key ? '3px solid var(--accent)' : '3px solid transparent' }}
            onClick={() => setTab(t.key)}
            onMouseEnter={e => { if (tab !== t.key) e.currentTarget.style.background = 'var(--surface-tertiary)'; }}
            onMouseLeave={e => { if (tab !== t.key) e.currentTarget.style.background = 'transparent'; }}
          >
            {t.label}
          </div>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto" style={{ background: 'var(--background)' }}>
        {renderContent()}
      </div>
    </div>
  );
}

/* ===================== 通用 ===================== */
function GeneralSettings() {
  return (
    <div className="p-6">
      <h2 style={{color:'var(--foreground)',fontSize: "var(--fs-lg)",fontWeight:600,marginBottom: "0.25rem"}}>通用设置</h2>
      <p style={{color:'var(--muted)',fontSize: "var(--fs-sm)",marginBottom: "var(--fs-lg)"}}>基础配置项</p>
      <div style={{color:'var(--muted)',fontSize: "var(--fs-sm)"}}>通用配置（待实现）</div>
    </div>
  );
}

/* ===================== LLM ===================== */
function LLMSettings() {
  return (
    <div className="p-6">
      <h2 style={{color:'var(--foreground)',fontSize: "var(--fs-lg)",fontWeight:600,marginBottom: "0.25rem"}}>LLM 模型</h2>
      <p style={{color:'var(--muted)',fontSize: "var(--fs-sm)",marginBottom: "var(--fs-lg)"}}>配置 AI 语言模型参数</p>
      {['DeepSeek V4 Flash', 'Claude Sonnet 4.6', 'GPT-4o'].map(name => (
        <div key={name} className="mb-2 rounded" style={{ background: 'var(--surface-secondary)' }}>
          <div className="flex items-center justify-between px-3 py-2.5 cursor-pointer" style={{ color: 'var(--default-foreground)' }}>
            <span style={{ fontSize: "var(--fs-sm)" }}>{name}</span>
            <label className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" className="sr-only peer" defaultChecked={name === 'DeepSeek V4 Flash'} />
              <div className="w-8 h-4 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-3 after:w-3 after:transition-all" style={{ background: name === 'DeepSeek V4 Flash' ? 'var(--accent)' : 'var(--border)' }} />
            </label>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ===================== 界面 ===================== */
function InterfaceSettings() {
  const { setTheme: setHerouiTheme, theme: currentTheme } = useTheme();
  const [lang, setLang] = useState<'zh' | 'en'>(() => (localStorage.getItem('ui_lang') as 'zh' | 'en') || 'zh');
  const [theme, setThemeState] = useState<'light' | 'dark' | 'system'>(() => (localStorage.getItem('ui_theme') as 'light' | 'dark' | 'system') || 'dark');
  const [zoom, setZoom] = useState(() => parseInt(localStorage.getItem('ui_zoom') || '100'));

  // Preview: theme using HeroUI's useTheme
  useEffect(() => {
    const apply = (t: string) => {
      if (t === 'light') setHerouiTheme('light');
      else if (t === 'dark') setHerouiTheme('dark');
      else {
        // follow system
        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        setHerouiTheme(mq.matches ? 'dark' : 'light');
      }
    };
    apply(theme);

    if (theme === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      const handler = () => apply('system');
      mq.addEventListener('change', handler);
      return () => mq.removeEventListener('change', handler);
    }
  }, [theme, setHerouiTheme]);

  const setTheme = (t: 'light' | 'dark' | 'system') => {
    setThemeState(t);
    if (t === 'light') setHerouiTheme('light');
    else if (t === 'dark') setHerouiTheme('dark');
    else {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      setHerouiTheme(mq.matches ? 'dark' : 'light');
    }
  };

  // Preview: zoom
  useEffect(() => {
    const clamped = Math.max(50, Math.min(200, zoom));
    document.documentElement.style.fontSize = `${clamped}%`;
  }, [zoom]);

  const save = () => {
    localStorage.setItem('ui_lang', lang);
    localStorage.setItem('ui_theme', theme);
    localStorage.setItem('ui_zoom', String(Math.max(50, Math.min(200, zoom))));
    window.dispatchEvent(new Event('themechange'));
  };

  const RadioGroup = ({ options, value, onChange }: { options: { value: string; label: string }[]; value: string; onChange: (v: any) => void }) => (
    <div className="flex gap-2">
      {options.map(opt => (
        <button key={opt.value}
          style={{
            height: "2.25rem", paddingInline: "var(--fs-lg)", borderRadius: "0.375rem",
            border: value === opt.value ? 'none' : '1px solid var(--border)',
            background: value === opt.value ? 'var(--accent)' : 'var(--surface-secondary)',
            color: value === opt.value ? 'var(--accent-foreground)' : 'var(--default-foreground)',
            fontSize: "var(--fs-sm)", cursor: 'pointer', fontWeight: 400,
            whiteSpace: 'nowrap',
          }}
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );

  return (
    <div className="p-6 flex flex-col min-h-0" style={{ height: '100%' }}>
      <h2 style={{color:'var(--foreground)',fontSize: "var(--fs-lg)",fontWeight:600,marginBottom: "0.25rem"}}>界面</h2>
      <p style={{color:'var(--muted)',fontSize: "var(--fs-sm)",marginBottom: "1.5rem"}}>界面语言和外观样式。切换后立即生效并持久化。</p>

      {/* UI 语言 */}
      <section style={{ marginBottom: "1.75rem" }}>
        <h3 style={{color:'var(--foreground)',fontSize: "var(--fs-md)",fontWeight:500,marginBottom: "0.625rem"}}>UI 语言</h3>
        <RadioGroup
          options={[{value:'en',label:'English'},{value:'zh',label:'中文'}]}
          value={lang} onChange={setLang}
        />
        <p style={{color:'var(--muted)',fontSize: "var(--fs-xs)",marginTop: "0.375rem"}}>
          只影响按钮、标签这些 UI 文案，不影响 AI 输出语言（那个在「输出偏好」里单独设置）。
        </p>
      </section>

      {/* 主题 */}
      <section style={{ marginBottom: "1.75rem" }}>
        <h3 style={{color:'var(--foreground)',fontSize: "var(--fs-md)",fontWeight:500,marginBottom: "0.625rem"}}>主题</h3>
        <RadioGroup
          options={[{value:'light',label:'浅色'},{value:'dark',label:'深色'},{value:'system',label:'跟随系统'}]}
          value={theme} onChange={setTheme}
        />
        <p style={{color:'var(--muted)',fontSize: "var(--fs-xs)",marginTop: "0.375rem"}}>
          预览会立即生效。保存设置后会记住所选主题。跟随系统会使用操作系统的外观设置。
        </p>
      </section>

      {/* 界面缩放 */}
      <section style={{ marginBottom: "1.75rem" }}>
        <h3 style={{color:'var(--foreground)',fontSize: "var(--fs-md)",fontWeight:500,marginBottom: "0.625rem"}}>界面缩放</h3>
        <div className="flex items-center gap-2">
          <button onClick={() => setZoom(z => Math.max(50, Math.min(200, z - 10)))}
            style={{ width: "2.25rem", height: "2.25rem", borderRadius: "0.375rem", border:'1px solid var(--border)', background:'var(--surface-secondary)', color:'var(--default-foreground)', fontSize: "1.125rem", cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center' }}>
            −
          </button>
          <div style={{ width: "6.875rem", height: "2.25rem", borderRadius: "0.375rem", border:'1px solid var(--border)', background:'var(--surface-secondary)', display:'flex', alignItems:'center', justifyContent:'center', fontSize: "var(--fs-md)" }}>
            <input
              style={{ width: "3.125rem", background:'transparent', border:'none', color:'var(--foreground)', fontSize: "var(--fs-md)", textAlign:'right', outline:'none' }}
              value={zoom}
              onChange={e => {
                const v = parseInt(e.target.value);
                if (!isNaN(v)) setZoom(Math.max(50, Math.min(200, v)));
              }}
            />
            <span style={{ color:'var(--muted)', marginLeft: "0.125rem" }}>%</span>
          </div>
          <button onClick={() => setZoom(z => Math.max(50, Math.min(200, z + 10)))}
            style={{ width: "2.25rem", height: "2.25rem", borderRadius: "0.375rem", border:'1px solid var(--border)', background:'var(--surface-secondary)', color:'var(--default-foreground)', fontSize: "1.125rem", cursor:'pointer', display:'flex', alignItems:'center', justifyContent:'center' }}>
            +
          </button>
        </div>
        <p style={{color:'var(--muted)',fontSize: "var(--fs-xs)",marginTop: "0.375rem"}}>
          缩放应用内文字和基于 rem 的间距。少数固定像素面板会保留实际尺寸限制。
        </p>
      </section>

      {/* Spacer + Save */}
      <div className="flex-1" />
      <div className="flex items-center justify-between pt-4 border-t" style={{ borderColor:'var(--border)' }}>
        <span style={{ color:'var(--muted)', fontSize: "var(--fs-sm)" }}>改动会在保存后应用。</span>
        <button onClick={save}
          style={{ height: "2.25rem", background:'var(--accent)', color:'var(--accent-foreground)', border:'none', borderRadius: "0.5rem", padding:'0 24px', fontSize: "var(--fs-md)", fontWeight:500, cursor:'pointer' }}>
          保存
        </button>
      </div>
    </div>
  );
}
