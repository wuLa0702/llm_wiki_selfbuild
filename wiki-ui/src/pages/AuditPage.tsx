import { useEffect, useState } from 'react';
import { showToast } from '../components/Toast';

interface BrokenLink { source: string; target: string; }
interface LintResult { broken_links?: BrokenLink[]; summary?: string; }

export default function AuditPage() {
  const [result, setResult] = useState<LintResult | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  useEffect(() => {
    fetch('/v1/lint?semantic=false').then(r => r.json()).then(setResult).catch(() => {});
  }, []);

  const links = result?.broken_links || [];

  return (
    <div className="flex-1 flex flex-col" style={{ background: 'var(--background)' }}>
      {/* Top toolbar */}
      <div className="flex items-center gap-3 px-4 py-2 border-b" style={{ borderColor: 'var(--border)' }}>
        <input type="checkbox" onChange={e => setSelected(e.target.checked ? new Set(links.map((_, i) => i)) : new Set())} />
        <button className="text-xs px-2 py-1 rounded" style={{ background:'var(--accent)', color:'var(--accent-foreground)', border:'none', cursor:'pointer' }}>修复选中项</button>
        <button className="text-xs px-2 py-1 rounded" style={{ background:'var(--surface-secondary)', color:'var(--muted)', border:'1px solid #333', cursor:'pointer' }}>移入待审阅</button>
        <button className="text-xs px-2 py-1 rounded" style={{ background:'var(--surface-secondary)', color:'var(--muted)', border:'1px solid #333', cursor:'pointer' }}>忽略选中项</button>
        <span style={{ color: 'var(--muted)', fontSize: "var(--fs-xs)", marginLeft: 'auto' }}>警告 ({links.length})</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {links.length === 0 ? (
          <div className="flex items-center justify-center h-full" style={{ color: 'var(--muted)' }}>
            <div className="text-center"><div style={{fontSize:32,marginBottom: "0.5rem",opacity:0.4}}>✅</div><p style={{fontSize:14}}>未发现断链</p></div>
          </div>
        ) : (
          <div className="space-y-2">
            {links.map((link, i) => (
              <div key={i} className="flex items-start gap-3 p-3 rounded" style={{ background: 'var(--surface-secondary)' }}>
                <input type="checkbox" checked={selected.has(i)} onChange={() => {
                  setSelected(prev => { const n = new Set(prev); n.has(i) ? n.delete(i) : n.add(i); return n; });
                }} style={{ marginTop: "2px" }} />
                <div className="flex-1 min-w-0">
                  <div style={{ color: 'var(--foreground)', fontSize: "var(--fs-sm)" }}>{link.source}</div>
                  <div style={{ color: 'var(--muted)', fontSize: "var(--fs-xs)", marginTop: "2px" }}>
                    <span style={{ color: 'var(--danger)' }}>失效链接</span> → {link.target}
                  </div>
                </div>
                <div className="flex gap-1">
                  <button className="text-xs px-2 py-1 rounded" style={{ background:'var(--accent)', color:'var(--accent-foreground)', border:'none', cursor:'pointer' }}>打开</button>
                  <button className="text-xs px-2 py-1 rounded" style={{ background:'var(--surface-secondary)', color:'var(--muted)', border:'1px solid #333', cursor:'pointer' }}>修复</button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
