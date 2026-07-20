import { useEffect, useState } from 'react';
import { Card, CardHeader, CardContent, Chip, Link, Button, Tooltip } from '@heroui/react';
import MarkdownRenderer from './MarkdownRenderer';
import { stripFrontmatter } from '../utils/markdown';

interface Props { path: string | null; onBack?: () => void; onNavigate?: (path: string) => void; }
interface Meta {
  title: string;
  page_type: string;
  created_at: string;
  links: string[];
  backlinks: string[];
  tags?: string[];
  source_file?: string;
}

function fmtDate(s: string) { return s?.slice(0, 10) || ''; }

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
    // API expects paths relative to wiki/ root (no "wiki/" prefix)
    const pp = path.startsWith('wiki/') ? path.slice(5) : path;
    fetch(`/v1/pages/${encodeURIComponent(pp)}`)
      .then(r => r.json())
      .then(d => {
        if (d.content !== undefined) {
          setRaw(d.content);
          setMeta({
            title: d.title, page_type: d.page_type,
            created_at: d.created_at,
            links: d.links || [], backlinks: d.backlinks || [],
            tags: d.tags || [],
            source_file: d.source_file,
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
      {/* Layer 1: Sticky Card — bordered variant for visible separation */}
      <Card variant="default" className="flex-shrink-0">
        <CardHeader className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0 space-y-1">
            <div className="flex items-center gap-2">
              <Chip size="sm" variant="flat" color={meta?.page_type === 'entity' ? 'primary' : meta?.page_type === 'concept' ? 'secondary' : 'default'}>
                {typeLabel[meta?.page_type || ''] || meta?.page_type || 'page'}
              </Chip>
              <h1 className="text-base font-semibold truncate">{meta?.title || path.split('/').pop()}</h1>
            </div>
            <div className="flex items-center gap-2 flex-wrap text-xs text-default-500">
              <span>创建 {fmtDate(meta?.created_at || '')}</span>
              {meta?.tags && meta.tags.length > 0 && meta.tags.map(t => (
                <Chip key={t} size="sm" variant="flat">{t}</Chip>
              ))}
            </div>
          </div>

          {/* Zone 4: Action buttons */}
          <div className="flex gap-1 flex-shrink-0">
            <Button size="sm" variant="ghost" onPress={() => { setEditContent(raw); setEditing(true); }}>编辑</Button>
            {onBack && <Button size="sm" variant="ghost" onPress={onBack}>✕</Button>}
          </div>
        </CardHeader>

        <CardContent className="space-y-3">
          {/* Zone 2: Source traceability */}
          {meta?.source_file && (
            <div>
              <p className="text-xs text-default-400 font-medium mb-0.5">📂 来源溯源</p>
              <Tooltip content={meta.source_file} delay={300}>
                <p className="text-xs text-default-500 truncate cursor-default">{meta.source_file}</p>
              </Tooltip>
            </div>
          )}

          {/* Zone 3: Bidirectional references */}
          {meta && (meta.links.length > 0 || meta.backlinks.length > 0) && (
            <div className="space-y-1">
              {meta.links.length > 0 && (
                <div className="flex items-center gap-1 flex-wrap">
                  <span className="text-xs text-default-400 font-medium flex-shrink-0">🔗 正向引用 ({meta.links.length})</span>
                  {meta.links.map(l => (
                    <Link key={l} size="sm" className="text-xs cursor-pointer" onPress={() => nav(l)}>
                      {(l.split('/').pop() || l).replace(/\.md$/i, '')}
                    </Link>
                  ))}
                </div>
              )}
              {meta.backlinks.length > 0 && (
                <div className="flex items-center gap-1 flex-wrap">
                  <span className="text-xs text-default-400 font-medium flex-shrink-0">🔙 反向引用 ({meta.backlinks.length})</span>
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

      {/* Layer 2: Markdown body — scrollable, frontmatter stripped */}
      <div className="flex-1 overflow-y-auto p-6">
        {editing ? (
          <textarea className="w-full h-full resize-none outline-none rounded-lg p-4 text-sm font-mono" style={{ background:'var(--surface)', color:'var(--default-foreground)', border:'1px solid var(--border)', minHeight:'25rem' }}
            value={editContent} onChange={e => setEditContent(e.target.value)} />
        ) : (
          <MarkdownRenderer content={stripFrontmatter(raw)} onNavigate={onNavigate} plainLinks />
        )}
      </div>
    </div>
  );
}
