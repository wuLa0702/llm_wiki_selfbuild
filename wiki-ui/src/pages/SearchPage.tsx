import { useState } from 'react';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);

  const search = async () => {
    if (!query.trim()) return;
    try {
      const r = await fetch('/v1/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), k: 20, method: 'hybrid' }),
      });
      const d = await r.json();
      setResults(d.results || []);
    } catch {}
  };

  return (
    <div className="flex-1 flex flex-col" style={{ background: 'var(--background)' }}>
      <div className="p-4 border-b" style={{ borderColor: 'var(--border)' }}>
        <input
          className="w-full px-3 py-2.5 rounded text-sm outline-none"
          style={{ background: 'var(--surface-secondary)', color: 'var(--default-foreground)', border: '1px solid #333' }}
          placeholder="搜索 Wiki 页面...(Enter to search)"
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && search()}
        />
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {results.length === 0 ? (
          <div className="flex items-center justify-center h-full" style={{ color: 'var(--muted)' }}>
            <div className="text-center">
              <div style={{ fontSize: "2rem", marginBottom: "0.5rem", opacity: 0.4 }}>🔍</div>
              <p style={{ fontSize: "var(--fs-md)" }}>Press Enter to search</p>
            </div>
          </div>
        ) : (
          <div className="space-y-2">
            {results.map((r, i) => (
              <div key={i} className="p-3 rounded" style={{ background: 'var(--surface-secondary)' }}>
                <div style={{ color: '#FFF', fontSize: "var(--fs-sm)", fontWeight: 500 }}>{r.title || r.path}</div>
                <div style={{ color: 'var(--muted)', fontSize: "var(--fs-xs)" }}>{r.path}</div>
                {r.snippet && <div style={{ color: 'var(--default-foreground)', fontSize: "var(--fs-sm)", marginTop: "0.25rem" }}>{r.snippet}</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
