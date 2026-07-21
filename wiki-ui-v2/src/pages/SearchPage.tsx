import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, FileText, Brain } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import EmptyState from '@/components/shared/EmptyState';

interface SearchResult {
  path: string;
  title?: string;
  snippet?: string;
  score?: number;
}

type SearchMethod = 'bm25' | 'hybrid';

export default function SearchPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [method, setMethod] = useState<SearchMethod>('bm25');

  const methodLabel = method === 'hybrid' ? 'Hybrid' : 'BM25';

  /* Escape special regex chars and build highlight segments */
  const highlightSnippet = (text: string, keyword: string): React.ReactNode => {
    if (!keyword.trim()) return text;
    const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const parts = text.split(new RegExp(`(${escaped})`, 'gi'));
    return parts.map((part, i) =>
      part.toLowerCase() === keyword.toLowerCase()
        ? <mark key={i} className="bg-yellow-200/60 dark:bg-yellow-500/25 text-inherit rounded-sm px-0.5">{part}</mark>
        : part
    );
  };

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const r = await fetch('/v1/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: query.trim(), k: 20, method }),
      });
      const d = await r.json();
      setResults(d.results || []);
    } catch {}
    setLoading(false);
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Search bar area */}
      <div className="flex-shrink-0 border-b border-border bg-card">
        <div className="max-w-2xl mx-auto p-4 space-y-3">
          {/* Semantic search toggle */}
          <div className="flex items-center gap-3">
            <button
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-full border transition-all cursor-pointer ${
                method === 'hybrid'
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border text-muted-foreground hover:text-foreground hover:bg-accent'
              }`}
              onClick={() => setMethod(method === 'hybrid' ? 'bm25' : 'hybrid')}
            >
              <Brain className={`h-3.5 w-3.5 ${method === 'hybrid' ? '' : 'opacity-50'}`} />
              语义搜索
            </button>
            <span className="text-[11px] text-muted-foreground/60">
              开启后使用向量语义搜索，结果更相关但速度较慢
            </span>
          </div>

          {/* Search input row */}
          <div className="flex gap-2">
            <Input
              placeholder="搜索知识库... (Enter 检索)"
              value={query}
              onChange={e => setQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && search()}
              className="flex-1"
            />
            <Button onClick={search} disabled={loading || !query.trim()}>
              <Search className="h-4 w-4 mr-1" />
              {loading ? '搜索中...' : '搜索'}
            </Button>
          </div>
        </div>
      </div>

      {/* Results */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="max-w-2xl mx-auto">
          {loading ? (
            <div className="space-y-3">
              {[1,2,3,4].map(i => (
                <div key={i} className="p-3 rounded-lg border border-border">
                  <Skeleton className="h-4 w-48 mb-2" />
                  <Skeleton className="h-3 w-32 mb-2" />
                  <Skeleton className="h-8 w-full" />
                </div>
              ))}
            </div>
          ) : results.length > 0 ? (
            <div className="space-y-2">
              {results.map((r, i) => (
                <div key={i} className="p-3 rounded-lg border border-border hover:bg-accent/50 transition-colors cursor-pointer"
                  onClick={() => navigate(`/wiki?path=${encodeURIComponent(r.path)}`)}>
                  <div className="flex items-center gap-2 mb-1">
                    <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    <span className="text-sm font-medium">{r.title || r.path.split('/').pop()}</span>
                    {r.score && <Badge variant="outline" className="text-[10px] ml-auto">{r.score.toFixed(2)}</Badge>}
                  </div>
                  <div className="text-xs text-muted-foreground mb-1">{r.path}</div>
                  {r.snippet && (
                    <div className="text-xs text-foreground/80 line-clamp-2">
                      {highlightSnippet(r.snippet, query)}
                    </div>
                  )}
                </div>
              ))}
              {/* Method badge in results footer */}
              <div className="text-center pt-2">
                <Badge variant="secondary" className="text-[10px]">
                  {methodLabel} · {results.length} 条结果
                </Badge>
              </div>
            </div>
          ) : (
            <EmptyState
              icon={Search}
              title="搜索知识库"
              desc={`输入关键词搜索 Wiki 页面 · 当前模式: ${methodLabel}`}
            />
          )}
        </div>
      </div>
    </div>
  );
}
