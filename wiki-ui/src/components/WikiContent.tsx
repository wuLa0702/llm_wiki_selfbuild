import { useEffect, useState } from 'react';
import { Chip, Link, Button } from '@heroui/react';
import MarkdownRenderer from './MarkdownRenderer';

interface Props { path: string | null; onBack?: () => void; onNavigate?: (path: string) => void; }
interface Meta { title: string; page_type: string; created_at: string; updated_at: string; word_count: number; links: string[]; backlinks: string[]; }

function fmtDate(s: string) { return s?.slice(0, 10) || ''; }

export default function WikiContent({ path, onBack, onNavigate }: Props) {
  const [raw, setRaw] = useState('');
  const [meta, setMeta] = useState<Meta | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState('');

  useEffect(() => {
    if (!path) return;
    setLoading(true); setError(''); setRaw(''); setMeta(null); setEditing(false);
    const pagePath = path.startsWith('wiki/') || path.startsWith('raw/') ? path : `wiki/${path}`;
    fetch(`/v1/pages/${encodeURIComponent(pagePath)}`)
      .then(r => r.json())
      .then(d => {
        if (d.content !== undefined) {
          setRaw(d.content);
          setMeta({
            title: d.title, page_type: d.page_type,
            created_at: d.created_at, updated_at: d.updated_at,
            word_count: d.word_count, links: d.links || [], backlinks: d.backlinks || [],
          });
        } else throw new Error();
      })
      .catch(() => {
        fetch(`/v1/file-content?path=${encodeURIComponent(pagePath)}`)
          .then(r => r.json())
          .then(d => { if (d.content !== undefined) setRaw(d.content); else setError('无法加载页面'); })
          .catch(e => setError(e.message));
      })
      .finally(() => setLoading(false));
  }, [path]);

  const startEdit = () => { setEditContent(raw); setEditing(true); };
  const cancelEdit = () => { setEditing(false); };
  const saveEdit = async () => {
    try {
      await fetch(`/v1/file-content`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ path, content: editContent }) });
      setRaw(editContent); setEditing(false);
    } catch {}
  };

  if (!path) return (
    <div className="flex-1 flex items-center justify-center text-muted-foreground">
      <div className="text-center"><div className="text-3xl mb-2 opacity-30">📂</div><p className="text-sm">Select a file to preview</p></div>
    </div>
  );
  if (loading) return (
    <div className="flex-1 flex items-center justify-center text-muted-foreground"><div className="text-center"><div className="text-xl mb-2">⏳</div><p className="text-sm">加载中...</p></div></div>
  );
  if (error) return (
    <div className="flex-1 flex items-center justify-center text-danger"><div className="text-center"><p className="text-sm">{error}</p>{onBack && <button className="mt-2 text-xs underline text-default-foreground" onClick={onBack}>返回</button>}</div></div>
  );

  const fileName = path.split('/').pop() || '';
  const nav = (p: string) => onNavigate?.(p);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Top bar */}
      <div className="flex items-center justify-between px-4 border-b flex-shrink-0" style={{ borderColor:'var(--border)', background:'var(--surface)', height:'2.625rem' }}>
        <span style={{ color:'var(--foreground)', fontSize:'var(--fs-md)', fontWeight:500 }}>📄 {fileName}</span>
        <div className="flex gap-2 items-center">
          {editing ? (
            <>
              <Button size="sm" color="primary" onPress={saveEdit}>保存</Button>
              <Button size="sm" variant="ghost" onPress={cancelEdit}>取消</Button>
            </>
          ) : (
            <Button size="sm" variant="ghost" onPress={startEdit}>编辑</Button>
          )}
          {onBack && <Button size="sm" variant="ghost" onPress={onBack}>✕</Button>}
        </div>
      </div>

      {/* Info card — fixed */}
      {meta && (
        <div className="px-4 py-3 border-b flex-shrink-0 space-y-2" style={{ background:'var(--surface)', borderColor:'var(--border)' }}>
          {/* Row 1: metadata */}
          <div className="flex items-center gap-3 text-xs text-default-500 flex-wrap">
            <Chip size="sm" variant="flat">{meta.page_type}</Chip>
            <span>创建 {fmtDate(meta.created_at)}</span>
            <span>更新 {fmtDate(meta.updated_at)}</span>
            <span>{meta.word_count} 字</span>
          </div>

          {/* Row 2: Related links */}
          {(meta.links.length > 0 || meta.backlinks.length > 0) && (
            <div className="flex items-start gap-6 text-xs">
              {meta.links.length > 0 && (
                <div className="flex items-center gap-1 flex-wrap">
                  <span className="text-default-400 font-medium flex-shrink-0">🔗 引用 ({meta.links.length})</span>
                  {meta.links.map(l => {
                    const label = (l.split('/').pop() || l).replace(/\.md$/i, '');
                    return <Link key={l} size="sm" className="text-xs cursor-pointer" onPress={() => nav(l)}>{label}</Link>;
                  })}
                </div>
              )}
              {meta.backlinks.length > 0 && (
                <div className="flex items-center gap-1 flex-wrap">
                  <span className="text-default-400 font-medium flex-shrink-0">🔙 被引用 ({meta.backlinks.length})</span>
                  {meta.backlinks.map(l => {
                    const label = (l.split('/').pop() || l).replace(/\.md$/i, '');
                    return <Link key={l} size="sm" className="text-xs cursor-pointer" onPress={() => nav(l)}>{label}</Link>;
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6" style={{ background:'var(--background)' }}>
        {editing ? (
          <textarea className="w-full h-full resize-none outline-none rounded-lg p-4 text-sm font-mono" style={{ background:'var(--surface)', color:'var(--default-foreground)', border:'1px solid var(--border)', minHeight:400 }}
            value={editContent} onChange={e => setEditContent(e.target.value)} />
        ) : (
          <MarkdownRenderer content={raw} onNavigate={onNavigate} plainLinks />
        )}
      </div>
    </div>
  );
}
