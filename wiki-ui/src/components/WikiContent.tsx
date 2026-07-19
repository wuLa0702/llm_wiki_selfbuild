import { useEffect, useState, useRef } from 'react';
import { createRoot } from 'react-dom/client';
import { Tooltip } from '@heroui/react';
import { renderMarkdown } from '../utils/markdown';

interface Props { path: string | null; onBack?: () => void; onNavigate?: (path: string) => void; }

export default function WikiContent({ path, onBack, onNavigate }: Props) {
  const [raw, setRaw] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  const tooltipsRef = useRef<(() => void)[]>([]);

  useEffect(() => {
    if (!path) return;
    setLoading(true); setError(''); setRaw(''); setEditing(false);
    // Try pages API first, fall back to file-content
    const pagePath = path.startsWith('wiki/') || path.startsWith('raw/') ? path : `wiki/${path}`;
    fetch(`/v1/pages/${encodeURIComponent(pagePath)}`)
      .then(r => r.json())
      .then(d => { if (d.content !== undefined) { setRaw(d.content); return; } throw new Error(); })
      .catch(() => {
        // Fallback to file-content (works for any wiki/ raw/ path)
        fetch(`/v1/file-content?path=${encodeURIComponent(pagePath)}`)
          .then(r => r.json())
          .then(d => { if (d.content !== undefined) setRaw(d.content); else setError('无法加载页面'); })
          .catch(e => setError(e.message));
      })
      .finally(() => setLoading(false));
  }, [path]);

  useEffect(() => {
    const el = ref.current; if (!el || !onNavigate) return;
    const h = (e: Event) => {
      const t = (e.target as HTMLElement).closest('.wikilink');
      if (t) { e.preventDefault(); const p = t.getAttribute('data-wiki-path'); if (p) onNavigate(p); }
    };
    el.addEventListener('click', h);
    return () => el.removeEventListener('click', h);
  }, [raw, onNavigate]);

  // Wrap wikilinks with HeroUI Tooltip (portal-based)
  useEffect(() => {
    // Cleanup previous tooltips
    tooltipsRef.current.forEach(fn => fn());
    tooltipsRef.current = [];

    const el = ref.current;
    if (!el) return;

    // Wait for DOM to settle
    const timer = setTimeout(() => {
      el.querySelectorAll('.wikilink').forEach(link => {
        const path = link.getAttribute('data-wiki-path') || '';
        link.removeAttribute('title'); // suppress native tooltip

        const wrapper = document.createElement('span');
        wrapper.style.display = 'inline';
        link.parentNode?.insertBefore(wrapper, link);
        wrapper.appendChild(link);

        const root = createRoot(wrapper);
        root.render(<Tooltip content={path} delay={200} closeDelay={100}><span /></Tooltip>);
        tooltipsRef.current.push(() => root.unmount());
      });
    }, 0);

    return () => clearTimeout(timer);
  }, [raw]);

  const startEdit = () => { setEditContent(raw); setEditing(true); };
  const cancelEdit = () => { setEditing(false); };
  const saveEdit = async () => {
    try {
      await fetch(`/v1/file-content`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path, content: editContent }),
      });
      setRaw(editContent);
      setEditing(false);
    } catch {}
  };

  if (!path) return (
    <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--muted)' }}>
      <div className="text-center"><div style={{fontSize:36,marginBottom: "0.5rem",opacity:0.3}}>📂</div><p style={{fontSize:14}}>Select a file to preview</p></div>
    </div>
  );

  if (loading) return (
    <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--muted)' }}>
      <div className="text-center"><div style={{fontSize:24,marginBottom: "0.5rem"}}>⏳</div><p style={{fontSize:14}}>加载中...</p></div>
    </div>
  );

  if (error) return (
    <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--danger)' }}>
      <div className="text-center"><p style={{fontSize:14}}>{error}</p>{onBack && <button style={{marginTop:8,fontSize: "var(--fs-sm)",color:'var(--accent)',background:'none',border:'none',cursor:'pointer',textDecoration:'underline'}} onClick={onBack}>返回</button>}</div>
    </div>
  );

  const fileName = path.split('/').pop() || '';

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Top bar with buttons */}
      <div className="flex items-center justify-between px-4 border-b flex-shrink-0" style={{ borderColor: 'var(--border)', background: 'var(--surface)', height: "2.625rem" }}>
        <span style={{ color: 'var(--foreground)', fontSize: "var(--fs-md)", fontWeight: 500 }}>📄 {fileName}</span>
        <div className="flex gap-2 items-center">
          {editing ? (
            <>
              <button onClick={saveEdit} style={{ height: "2rem", background:'var(--accent)', color:'var(--accent-foreground)', border:'none', borderRadius: "0.25rem", padding:'0 14px', fontSize: "var(--fs-sm)", cursor:'pointer', display:'inline-flex', alignItems:'center' }}>保存</button>
              <button onClick={cancelEdit} style={{ height: "2rem", background:'var(--surface-secondary)', color:'var(--muted)', border:'1px solid #333', borderRadius: "0.25rem", padding:'0 10px', fontSize: "var(--fs-sm)", cursor:'pointer', display:'inline-flex', alignItems:'center' }}>取消</button>
            </>
          ) : (
            <button onClick={startEdit} style={{ height: "2rem", background:'var(--surface-secondary)', color:'var(--muted)', border:'1px solid #333', borderRadius: "0.25rem", padding:'0 10px', fontSize: "var(--fs-sm)", cursor:'pointer', display:'inline-flex', alignItems:'center' }}>编辑</button>
          )}
          {onBack && <button onClick={onBack} style={{ height: "2rem", background:'none', border:'none', color:'var(--muted)', fontSize: "var(--fs-md)", cursor:'pointer', display:'inline-flex', alignItems:'center' }}>✕</button>}
        </div>
      </div>

      {/* Content or editor */}
      <div className="flex-1 overflow-y-auto p-6" ref={ref} style={{ background: 'var(--background)' }}>
        {editing ? (
          <textarea
            className="w-full h-full resize-none outline-none"
            style={{ background: 'var(--surface)', color: 'var(--default-foreground)', border: '1px solid #333', borderRadius: "0.5rem", padding: "var(--fs-lg)", fontSize: "var(--fs-sm)", fontFamily: 'monospace', lineHeight: 1.6, minHeight: 400 }}
            value={editContent}
            onChange={e => setEditContent(e.target.value)}
          />
        ) : (
          <div className="md-content" dangerouslySetInnerHTML={{ __html: renderMarkdown(raw, onNavigate) }} />
        )}
      </div>
    </div>
  );
}
