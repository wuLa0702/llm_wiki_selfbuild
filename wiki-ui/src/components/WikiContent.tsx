import { useEffect, useState } from 'react';
import { Card, CardHeader, CardContent, Chip, Link, Button, Tooltip } from '@heroui/react';
import MarkdownRenderer from './MarkdownRenderer';

interface Props { path: string | null; onBack?: () => void; onNavigate?: (path: string) => void; }
interface Meta { title: string; page_type: string; created_at: string; updated_at: string; word_count: number; links: string[]; backlinks: string[]; tags?: string[]; }

function fmt(s: string) { return s?.slice(0, 10) || ''; }

const typeLabel: Record<string, string> = { entity:'实体', concept:'概念', source:'引用源', query:'检索问句', comparison:'整合摘要' };

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
    const pp = path.startsWith('wiki/') || path.startsWith('raw/') ? path : `wiki/${path}`;
    fetch(`/v1/pages/${encodeURIComponent(pp)}`)
      .then(r => r.json())
      .then(d => {
        if (d.content !== undefined) {
          setRaw(d.content);
          setMeta({
            title: d.title, page_type: d.page_type,
            created_at: d.created_at, updated_at: d.updated_at,
            word_count: d.word_count, links: d.links || [], backlinks: d.backlinks || [],
            tags: d.tags || [],
          });
        } else throw new Error();
      })
      .catch(() => {
        fetch(`/v1/file-content?path=${encodeURIComponent(pp)}`)
          .then(r => r.json()).then(d => { if (d.content !== undefined) setRaw(d.content); else setError('无法加载页面'); })
          .catch(e => setError(e.message));
      })
      .finally(() => setLoading(false));
  }, [path]);

  const nav = (p: string) => onNavigate?.(p);

  if (!path) return <div className="flex-1 flex items-center justify-center text-default-400"><div className="text-center"><div className="text-3xl mb-2 opacity-30">📂</div><p className="text-sm">Select a file to preview</p></div></div>;
  if (loading) return <div className="flex-1 flex items-center justify-center text-default-400"><p className="text-sm">⏳ 加载中...</p></div>;
  if (error) return <div className="flex-1 flex items-center justify-center text-danger"><div className="text-center"><p className="text-sm">{error}</p>{onBack && <Button size="sm" variant="light" onPress={onBack}>返回</Button>}</div></div>;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Info card — fixed top, HeroUI Card + CardBody */}
      <Card variant="bordered" className="rounded-none flex-shrink-0 border-l-0 border-r-0">
        <CardHeader className="flex items-center justify-between pb-0">
          <div className="flex items-center gap-2 min-w-0">
            <Chip size="sm" variant="flat" color={meta?.page_type === 'entity' ? 'primary' : meta?.page_type === 'concept' ? 'secondary' : 'default'}>
              {typeLabel[meta?.page_type || ''] || meta?.page_type || 'page'}
            </Chip>
            <h1 className="text-base font-semibold truncate">{meta?.title || path.split('/').pop()}</h1>
          </div>
          <div className="flex gap-1 flex-shrink-0">
            <Button size="sm" variant="ghost" onPress={() => { setEditContent(raw); setEditing(true); }}>编辑</Button>
            {onBack && <Button size="sm" variant="ghost" onPress={onBack}>✕</Button>}
          </div>
        </CardHeader>
        <CardContent className="py-2 space-y-2">
          {/* Row 1: Basic info */}
          <div className="flex items-center gap-2 text-xs text-default-500 flex-wrap">
            <span>创建 {fmt(meta?.created_at || '')}</span>
            <span>· 更新 {fmt(meta?.updated_at || '')}</span>
            <span>· {meta?.word_count || 0} 字</span>
            {meta?.tags && meta.tags.length > 0 && meta.tags.map(t => (
              <Chip key={t} size="sm" variant="flat" className="text-xs">{t}</Chip>
            ))}
          </div>

          {/* Row 2: Source path */}
          <div className="text-xs text-default-400 truncate flex items-center gap-1">
            <span className="flex-shrink-0">📁</span>
            <Tooltip content={path} delay={300}>
              <span className="truncate">{path}</span>
            </Tooltip>
          </div>

          {/* Row 3: Related links */}
          {meta && (meta.links.length > 0 || meta.backlinks.length > 0) && (
            <div className="flex items-start gap-4 text-xs flex-wrap">
              {meta.links.length > 0 && (
                <div className="flex items-center gap-1 flex-wrap">
                  <span className="text-default-400 font-medium flex-shrink-0">🔗 引用 ({meta.links.length})</span>
                  {meta.links.map(l => (
                    <Link key={l} size="sm" className="text-xs cursor-pointer" onPress={() => nav(l)}>
                      {(l.split('/').pop() || l).replace(/\.md$/i, '')}
                    </Link>
                  ))}
                </div>
              )}
              {meta.backlinks.length > 0 && (
                <div className="flex items-center gap-1 flex-wrap">
                  <span className="text-default-400 font-medium flex-shrink-0">🔙 被引用 ({meta.backlinks.length})</span>
                  {meta.backlinks.map(l => (
                    <Link key={l} size="sm" className="text-xs cursor-pointer" onPress={() => nav(l)}>
                      {(l.split('/').pop() || l).replace(/\.md$/i, '')}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Content — scrollable */}
      <div className="flex-1 overflow-y-auto p-6" style={{ background:'var(--background)' }}>
        {editing ? (
          <textarea className="w-full h-full resize-none outline-none rounded-lg p-4 text-sm font-mono" style={{ background:'var(--surface)', color:'var(--default-foreground)', border:'1px solid var(--border)', minHeight:'25rem' }}
            value={editContent} onChange={e => setEditContent(e.target.value)} />
        ) : (
          <MarkdownRenderer content={raw} onNavigate={onNavigate} plainLinks />
        )}
      </div>
    </div>
  );
}
