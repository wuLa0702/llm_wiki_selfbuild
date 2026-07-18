import { useEffect, useState, useRef } from 'react';

export default function GraphPage() {
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({ nodes: 0, links: 0 });
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    fetch('/v1/graph').then(r => r.json()).then(d => {
      const nodes = d.nodes || d.graph?.nodes || [];
      const links = d.links || d.graph?.links || [];
      setStats({ nodes: nodes.length, links: links.length });
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  return (
    <div className="flex-1 flex flex-col" style={{ background: 'var(--background)' }}>
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b" style={{ borderColor: 'var(--border)' }}>
        <span style={{ color: 'var(--muted)', fontSize: "var(--fs-xs)" }}>{stats.nodes} nodes / {stats.links} links</span>
        <div className="flex gap-2">
          {['Filter','Reset','View','Community'].map(label => (
            <button key={label} style={{ background:'var(--surface-secondary)', color:'var(--muted)', border:'1px solid #333', borderRadius: "0.25rem", padding:'2px 8px', fontSize: "var(--fs-xs)", cursor:'pointer' }}>
              {label}
            </button>
          ))}
        </div>
      </div>
      {/* Canvas */}
      <div className="flex-1 relative">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center" style={{ color: 'var(--muted)' }}>加载中...</div>
        ) : stats.nodes === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center" style={{ color: 'var(--muted)' }}>
            <div className="text-center"><div style={{fontSize:32,marginBottom: "0.5rem",opacity:0.4}}>🕸️</div><p style={{fontSize:14}}>没有可见节点</p></div>
          </div>
        ) : (
          <canvas ref={canvasRef} className="w-full h-full" />
        )}
      </div>
    </div>
  );
}
