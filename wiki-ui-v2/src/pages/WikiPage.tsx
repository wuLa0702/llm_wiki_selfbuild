import { useEffect, useState, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { FileText, FolderClosed, BookOpen, ArrowRight, ArrowLeft, Edit3, Save, X } from 'lucide-react';

/** 从 hash #L<number> 解析行号 */
function parseLineHash(): number | null {
  const hash = window.location.hash;
  const m = hash.match(/^#L(\d+)$/);
  return m ? parseInt(m[1], 10) : null;
}
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import EmptyState from '@/components/shared/EmptyState';
import {
  Sheet, SheetContent,
} from '@/components/ui/sheet';
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

const typeHexColor: Record<string, string> = {
  entity: '#3b82f6',
  concept: '#8b5cf6',
  source: '#10b981',
  query: '#f59e0b',
  comparison: '#ec4899',
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
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem('wiki-sidebar-wiki') || '{}'); } catch { return {}; }
  });
  const [treeLoading, setTreeLoading] = useState(true);

  // Page content state
  const [raw, setRaw] = useState('');
  const [meta, setMeta] = useState<PageMeta | null>(null);
  const [contentLoading, setContentLoading] = useState(false);
  const [contentError, setContentError] = useState('');
  // Edit state
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState('');
  const [isDirty, setIsDirty] = useState(false);
  const bodyRef = useRef('');

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

  // Persist expand/collapse state to localStorage
  useEffect(() => {
    localStorage.setItem('wiki-sidebar-wiki', JSON.stringify(expanded));
  }, [expanded]);

  /** 处理 hash 行号定位：搜索结果跳转 #L<line> */
  const scrollToLine = (line: number | null) => {
    if (!line) return;
    const el = document.getElementById(`L${line}`);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    // 短暂高亮效果
    el.classList.add('bg-yellow-200/40', 'dark:bg-yellow-500/20');
    setTimeout(() => {
      el.classList.remove('bg-yellow-200/40', 'dark:bg-yellow-500/20');
    }, 2500);
  };

  // 页面内容加载完后检测 hash 行号
  useEffect(() => {
    if (contentLoading || !selectedPage) return;
    const line = parseLineHash();
    if (line) {
      // 延迟一帧等 DOM 渲染完成
      requestAnimationFrame(() => {
        requestAnimationFrame(() => scrollToLine(line));
      });
    }
  }, [contentLoading, selectedPage]);

  // 监听 hash 变化（同页内跳转）
  useEffect(() => {
    const onHashChange = () => {
      scrollToLine(parseLineHash());
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const handleSelectPage = (path: string) => {
    setSearchParams({ path });
  };

  const toggleExpand = (path: string) => {
    setExpanded(prev => ({ ...prev, [path]: !prev[path] }));
  };

  const openEditor = () => {
    // Strip YAML frontmatter — only edit body, preserve metadata
    const body = raw.replace(/^---[\s\S]*?---\n*/, '').trimStart();
    setEditContent(body);
    bodyRef.current = body;
    setIsDirty(false);
    setSaveError('');
    setEditing(true);
  };

  const saveContent = async () => {
    if (!selectedPage) return;
    setSaving(true);
    setSaveError('');
    // Reconstruct: original frontmatter + edited body
    const fmMatch = raw.match(/^---[\s\S]*?---/);
    const reconstructed = fmMatch ? fmMatch[0] + '\n\n' + editContent.trimStart() : editContent;
    const pp = selectedPage.startsWith('wiki/') ? selectedPage.slice(5) : selectedPage;
    try {
      const r = await fetch(`/v1/pages/${encodeURIComponent(pp)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: reconstructed }),
      });
      if (!r.ok) throw new Error(`保存失败 (${r.status})`);
      setRaw(reconstructed);
      setIsDirty(false);
      setEditing(false);
    } catch (e: any) {
      setSaveError(e.message || '保存出错');
    } finally {
      setSaving(false);
    }
  };

  const handleClose = () => {
    if (isDirty && !window.confirm('内容已修改但未保存，确定关闭吗？')) return;
    setEditing(false);
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
    <>
    <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* File tree panel */}
      <div className="w-72 flex-shrink-0 border-r border-border bg-card flex flex-col min-h-0 overflow-hidden">
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
          <BookOpen className="h-4 w-4" />
          <span className="text-xs font-medium">知识库</span>
        </div>
        <div className="flex-1 overflow-y-scroll py-1">
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
      <div className="flex-1 flex flex-col min-h-0 min-w-0 overflow-hidden">
        {!selectedPage ? (
          <EmptyState icon={BookOpen} title="选择页面" desc="从左侧文件树中选择 Wiki 页面查看内容" />
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
                      <Button variant="outline" size="sm" className="h-7 text-xs gap-1" onClick={openEditor}>
                        <Edit3 className="h-3 w-3" /> 编辑
                      </Button>
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
            <div className={`flex-1 overflow-y-scroll px-4 pb-4 content-swap ${contentLoading ? 'content-swap-loading' : ''}`}>
              <div key={selectedPage} className="max-w-3xl mx-auto bg-card rounded-lg border border-border p-6 shadow-sm page-content-enter">
                <MarkdownRenderer
                  content={raw.replace(/^---[\s\S]*?---\n*/, '')}
                  onNavigate={handleSelectPage}
                  plainLinks
                  lineAnchors
                />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>

      {/* ── Edit Sheet ── */}
      <Sheet open={editing} onOpenChange={(v: boolean) => {
        if (!v && isDirty && !window.confirm('内容已修改但未保存，确定关闭吗？')) {
          setTimeout(() => setEditing(true), 50);
          return;
        }
        setEditing(false);
      }}>
        <SheetContent
          showCloseButton={false}
          className="flex flex-col w-full min-w-[480px] max-w-[90vw] 2xl:max-w-[1400px]"
        >
          {/* Sticky header with type color bar */}
          <div
            className="flex items-center gap-3 px-5 py-3.5 border-b border-border shrink-0"
            style={{
              borderLeft: `3px solid ${typeHexColor[meta?.page_type || 'entity'] || '#3b82f6'}`,
            }}
          >
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                {meta?.page_type && (
                  <span
                    className="text-[10px] font-semibold uppercase tracking-wider"
                    style={{ color: typeHexColor[meta.page_type] }}
                  >
                    {typeLabel[meta.page_type]}
                  </span>
                )}
                <span className="text-xs text-muted-foreground truncate">
                  {selectedPage?.split('/').pop()}
                </span>
              </div>
              <h2 className="text-sm font-semibold mt-0.5">编辑文档</h2>
            </div>
            <button
              className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
              onClick={handleClose}
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Scrollable editing area */}
          <div className="flex-1 overflow-y-auto px-5 py-4 min-h-0">
            <Textarea
              className="w-full h-full min-h-[400px] font-mono text-sm resize-none border-0 p-0 focus-visible:ring-0"
              value={editContent}
              onChange={e => {
                setEditContent(e.target.value);
                setIsDirty(e.target.value !== bodyRef.current);
              }}
              placeholder="在此编辑文档正文..."
            />
          </div>

          {saveError && (
            <div className="shrink-0 px-5 py-2 text-xs text-destructive bg-destructive/5 border-t border-border">
              {saveError}
            </div>
          )}

          {/* Sticky footer */}
          <div className="shrink-0 flex items-center justify-end gap-2 px-5 py-3 border-t border-border bg-popover">
            {isDirty && (
              <span className="text-[10px] text-muted-foreground mr-auto">⦿ 有未保存的修改</span>
            )}
            <Button variant="outline" size="sm" onClick={handleClose}>
              取消
            </Button>
            <Button size="sm" onClick={saveContent} disabled={saving || !editContent.trim()}>
              <Save className="h-3.5 w-3.5 mr-1" />
              {saving ? '保存中...' : '保存'}
            </Button>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
