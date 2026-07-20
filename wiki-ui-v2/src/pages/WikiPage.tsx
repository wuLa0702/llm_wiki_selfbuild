import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { FileText, FolderClosed, BookOpen, ArrowRight, ArrowLeft } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import MarkdownRenderer from '@/components/shared/MarkdownRenderer';

interface FileNode {
  type: 'file' | 'directory';
  size?: number;
  children?: Record<string, FileNode>;
}

interface PageMeta {
  title: string;
  page_type: string;
  created_at: string;
  links: string[];
  backlinks: string[];
  tags?: string[];
  source_file?: string;
}

function fmtDate(s: string) { return s?.slice(0, 10) || ''; }

const typeLabel: Record<string, string> = {
  entity: '实体', concept: '概念', source: '引用源',
  query: '检索问句', comparison: '整合摘要',
};

const typeColor: Record<string, string> = {
  entity: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800',
  concept: 'bg-violet-500/10 text-violet-600 dark:text-violet-400 border-violet-200 dark:border-violet-800',
  source: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-200 dark:border-emerald-800',
  query: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-200 dark:border-amber-800',
  comparison: 'bg-pink-500/10 text-pink-600 dark:text-pink-400 border-pink-200 dark:border-pink-800',
};

export default function WikiPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedPage = searchParams.get('path');

  // File tree state
  const [wikiTree, setWikiTree] = useState<Record<string, FileNode>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [treeLoading, setTreeLoading] = useState(true);

  // Page content state
  const [raw, setRaw] = useState('');
  const [meta, setMeta] = useState<PageMeta | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState('');

  // Load file tree
  useEffect(() => {
    fetch('/v1/file-tree')
      .then(r => r.json())
      .then(d => {
        setWikiTree(d.wiki?.children || {});
        setTreeLoading(false);
        // Auto-expand to show active path
        if (selectedPage) {
          const segments = selectedPage.split('/').slice(0, -1);
          const toExpand: Record<string, boolean> = {};
          let prefix = '';
          for (const seg of segments) {
            prefix = prefix ? `${prefix}/${seg}` : seg;
            toExpand[prefix] = true;
          }
          setExpanded(prev => ({ ...prev, ...toExpand }));
        }
      })
      .catch(() => setTreeLoading(false));
  }, []);

  // Load page content when selection changes
  useEffect(() => {
    if (!selectedPage) { setRaw(''); setMeta(null); setContentError(''); return; }
    setContentLoading(true); setContentError('');
    // Keep old content visible until new arrives — prevents flash on navigation
    const pp = selectedPage.startsWith('wiki/') ? selectedPage.slice(5) : selectedPage;
    fetch(`/v1/pages/${encodeURIComponent(pp)}`)
      .then(r => r.json())
      .then(d => {
        if (d.content !== undefined) {
          setRaw(d.content);
          setMeta({
            title: d.title, page_type: d.page_type,
            created_at: d.created_at,
            links: d.links || [], backlinks: d.backlinks || [],
            tags: d.tags || [], source_file: d.source_file,
          });
        } else throw new Error();
      })
      .catch(() => {
        // Fallback: use selectedPage (preserves wiki/ prefix for file-content)
        const filePath = selectedPage.startsWith('wiki/') ? selectedPage : `wiki/${selectedPage}`;
        fetch(`/v1/file-content?path=${encodeURIComponent(filePath)}`)
          .then(r => r.json()).then(d => {
            if (d.content !== undefined) setRaw(d.content);
            else setContentError(`无法加载页面: ${selectedPage?.split('/').pop() || ''} 不存在`);
          })
          .catch(e => setContentError(`加载失败: ${e.message}`));
      })
      .finally(() => setContentLoading(false));
  }, [selectedPage]);

  // Auto-expand tree when selection changes
  useEffect(() => {
    if (!selectedPage) return;
    const segments = selectedPage.split('/').slice(0, -1);
    const toExpand: Record<string, boolean> = {};
    let prefix = '';
    for (const seg of segments) {
      prefix = prefix ? `${prefix}/${seg}` : seg;
      toExpand[prefix] = true;
    }
    setExpanded(prev => ({ ...prev, ...toExpand }));
  }, [selectedPage]);

  const handleSelectPage = (path: string) => {
    setSearchParams({ path });
  };

  const toggleExpand = (path: string) => {
    setExpanded(prev => ({ ...prev, [path]: !prev[path] }));
  };

  const countFiles = (children: Record<string, FileNode>): number =>
    Object.values(children).reduce((acc, n) => acc + (n.type === 'file' ? 1 : countFiles(n.children || {})), 0);

  const renderTree = (children: Record<string, FileNode>, prefix = '', depth = 0): React.ReactNode => {
    const entries = Object.entries(children);
    if (!entries.length) return <></>;
    const indent = depth * 14; // 14px per level
    return (
      <ul className="list-none p-0 m-0">
        {entries.map(([name, node]) => {
          const fullPath = prefix ? `${prefix}/${name}` : name;
          if (node.type === 'directory') {
            const isOpen = expanded[fullPath];
            return (
              <li key={fullPath}>
                <div
                  className="flex items-center gap-2 px-2 py-1.5 cursor-pointer text-xs rounded hover:bg-accent/50 transition-colors duration-100"
                  style={{ paddingLeft: `${indent + 8}px` }}
                  onClick={() => toggleExpand(fullPath)}
                >
                  <span className={`text-[0.5rem] transition-transform shrink-0 ${isOpen ? 'rotate-90' : ''}`}>▶</span>
                  <div className="flex items-center justify-center w-5 h-5 rounded-md bg-secondary/50 shrink-0">
                    <FolderClosed className="h-3 w-3 text-muted-foreground" />
                  </div>
                  <span className="truncate flex-1">{name}</span>
                  <span className="text-muted-foreground text-[10px]">{countFiles(node.children || {})}</span>
                </div>
                {isOpen && node.children && renderTree(node.children, fullPath, depth + 1)}
              </li>
            );
          }
          const isActive = selectedPage && (fullPath === selectedPage || fullPath === `wiki/${selectedPage}`);
          return (
            <li key={fullPath}>
              <div
                className={`flex items-center gap-2 px-2 py-1.5 cursor-pointer text-xs rounded transition-colors duration-100 ${
                  isActive ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50'
                }`}
                style={{ paddingLeft: `${indent + 32}px` }}
                onClick={() => handleSelectPage(fullPath)}
              >
                <div className="flex items-center justify-center w-5 h-5 rounded-md bg-muted/50 shrink-0">
                  <FileText className="h-3 w-3 text-muted-foreground shrink-0" />
                </div>
                <span className="truncate">{name}</span>
              </div>
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <div className="flex flex-1 min-h-0">
      {/* File tree panel */}
      <div className="w-72 flex-shrink-0 border-r border-border bg-card flex flex-col min-h-0">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
          <BookOpen className="h-4 w-4" />
          <span className="text-xs font-medium">知识库</span>
        </div>
        <div className="flex-1 overflow-y-auto py-1">
          {treeLoading ? (
            <div className="space-y-1 p-3">
              {[1,2,3,4,5,6].map(i => <Skeleton key={i} className="h-5 w-full" />)}
            </div>
          ) : Object.keys(wikiTree).length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-8">
              <BookOpen className="h-6 w-6 mx-auto mb-1 opacity-30" />
              知识库还没有内容
            </div>
          ) : renderTree(wikiTree, 'wiki')}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex flex-col min-h-0 min-w-0">
        {!selectedPage ? (
          <div className="flex-1 flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <FileText className="h-8 w-8 mx-auto mb-2 opacity-30" />
              <p className="text-sm">从左侧选择文件查看</p>
            </div>
          </div>
        ) : contentLoading ? (
          <div className="flex-1 p-6 space-y-4">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-4 w-96" />
            <Skeleton className="h-32 w-full" />
            <Skeleton className="h-24 w-3/4" />
          </div>
        ) : contentError ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center max-w-md">
              <div className="w-12 h-12 rounded-xl bg-destructive/10 flex items-center justify-center mx-auto mb-3">
                <FileText className="h-5 w-5 text-destructive" />
              </div>
              <p className="text-sm font-medium text-destructive mb-1">页面不可用</p>
              <p className="text-xs text-muted-foreground">{contentError}</p>
              <p className="text-xs text-muted-foreground/60 mt-3">检查文件路径是否正确，或从左侧文件树重新选择</p>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col min-h-0">
            {/* Sticky header — floating card */}
            <div className="flex-shrink-0 px-4 mt-4 mb-2">
              <div className="max-w-3xl mx-auto">
              <Card className="rounded-xl shadow-sm border overflow-hidden">
                <div className="p-5">
                  {/* Row 1: icon + title + type + action */}
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-3 min-w-0 flex-1">
                      {/* Icon */}
                      {meta?.page_type && (
                        <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 shadow-sm ${
                          typeColor[meta.page_type]?.split(' ')[0] || 'bg-muted'
                        }`}>
                          <FileText className={`h-5 w-5 ${typeColor[meta.page_type]?.split(' ')[1] || ''}`} />
                        </div>
                      )}
                      <div className="min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          {meta?.page_type && (
                            <Badge variant="outline" className={`text-[10px] ${typeColor[meta.page_type] || ''}`}>
                              {typeLabel[meta.page_type] || meta.page_type}
                            </Badge>
                          )}
                          <h1 className="text-base font-semibold truncate">
                            {meta?.title || selectedPage.split('/').pop()}
                          </h1>
                        </div>
                        <div className="flex items-center gap-3 text-xs text-muted-foreground">
                          <span>创建 {fmtDate(meta?.created_at || '')}</span>
                          {meta?.source_file && (
                            <Tooltip>
                              <TooltipTrigger className="truncate max-w-[200px] cursor-default hover:text-foreground" render={<span />}>
                                📄 {meta.source_file}
                              </TooltipTrigger>
                              <TooltipContent>{meta.source_file}</TooltipContent>
                            </Tooltip>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Right action area */}
                    <div className="flex items-center gap-2 shrink-0">
                      {meta && (meta.links.length > 0 || meta.backlinks.length > 0) && (
                        <div className="flex items-center gap-2 text-xs px-2.5 py-1.5 rounded-lg bg-muted/50">
                          <span className="text-blue-600 dark:text-blue-400 font-medium">{meta.links.length}</span>
                          <span className="text-border/60">|</span>
                          <span className="text-purple-600 dark:text-purple-400 font-medium">{meta.backlinks.length}</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Row 2: tags */}
                  {meta?.tags && meta.tags.length > 0 && (
                    <div className="mt-3 flex items-center gap-1.5 flex-wrap">
                      {meta.tags.map(t => (
                        <Badge key={t} variant="secondary" className="text-[10px]">{t}</Badge>
                      ))}
                    </div>
                  )}

                  {/* Row 3: bidirectional links as chips */}
                  {meta && (meta.links.length > 0 || meta.backlinks.length > 0) && (
                    <div className="mt-6 space-y-6">
                      {meta.links.length > 0 && (
                        <div>
                          <span className="flex items-center gap-1 text-xs font-semibold text-muted-foreground mb-2">
                            <ArrowRight className="h-3.5 w-3.5" /> 正向引用 ({meta.links.length})
                          </span>
                          <div className="flex items-center gap-3 flex-wrap">
                            {meta.links.map(l => (
                              <Badge key={l} variant="outline"
                                className="text-[11px] cursor-pointer hover:brightness-90 transition-all bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-800"
                                onClick={() => handleSelectPage(l)}>
                                {(l.split('/').pop() || l).replace(/\.md$/i, '')}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                      {meta.backlinks.length > 0 && (
                        <div>
                          <span className="flex items-center gap-1 text-xs font-semibold text-muted-foreground mb-2">
                            <ArrowLeft className="h-3.5 w-3.5" /> 反向引用 ({meta.backlinks.length})
                          </span>
                          <div className="flex items-center gap-3 flex-wrap">
                            {meta.backlinks.map(l => (
                              <Badge key={l} variant="outline"
                                className="text-[11px] cursor-pointer hover:brightness-90 transition-all bg-purple-50 text-purple-600 border-purple-200 dark:bg-purple-950/30 dark:text-purple-400 dark:border-purple-800"
                                onClick={() => handleSelectPage(l)}>
                                {(l.split('/').pop() || l).replace(/\.md$/i, '')}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </Card>
              </div>
            </div>

            {/* Scrollable markdown body — floating card */}
            <div className={`flex-1 overflow-y-auto px-4 pb-4 content-swap ${contentLoading ? 'content-swap-loading' : ''}`}>
              <div key={selectedPage} className="max-w-3xl mx-auto bg-card rounded-lg border border-border p-6 shadow-sm page-content-enter">
                <MarkdownRenderer
                  content={raw.replace(/^---[\s\S]*?---\n*/, '')}
                  onNavigate={handleSelectPage}
                  plainLinks
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
