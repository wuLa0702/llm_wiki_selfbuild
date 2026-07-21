import { useEffect, useState, useRef } from 'react';
import { FileText, FolderClosed, Upload, Trash2, RefreshCw, Sparkles, Edit3, Save, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { Sheet, SheetContent, SheetClose } from '@/components/ui/sheet';
import { showToast } from '@/components/shared/Toast';
import MarkdownRenderer from '@/components/shared/MarkdownRenderer';
import EmptyState from '@/components/shared/EmptyState';

interface SourceItem {
  name: string; type: 'file' | 'directory'; path: string;
  size?: number; children?: SourceItem[];
}

interface QueueJob {
  job_id: string; source_path: string; status: string;
  error?: string; result_summary?: string;
}

const STATUS_ICON: Record<string, string> = {
  pending: '⏳', processing: '🔄', done: '✅', failed: '❌',
};

function countFiles(item: SourceItem): number {
  if (item.type === 'file') return 1;
  return (item.children || []).reduce((acc, c) => acc + countFiles(c), 0);
}

export default function SourcesPage() {
  const [tree, setTree] = useState<SourceItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [fileSize, setFileSize] = useState('');
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [jobs, setJobs] = useState<QueueJob[]>([]);
  const [editing, setEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [saving, setSaving] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const loadTree = () => {
    setLoading(true);
    fetch('/v1/sources/tree')
      .then(r => r.json())
      .then(d => { setTree(d.tree || []); setLoading(false); })
      .catch(() => { showToast('加载文件树失败', 'error'); setLoading(false); });
  };

  useEffect(() => { loadTree(); }, []);

  useEffect(() => {
    const fetchQueue = () => {
      fetch('/v1/ingest/queue/recent?limit=10')
        .then(r => r.json())
        .then(d => setJobs(d.jobs || []))
        .catch(() => {});
    };
    fetchQueue();
    const id = setInterval(fetchQueue, 5000);
    return () => clearInterval(id);
  }, []);

  const toggleDir = (path: string) => {
    setExpanded(prev => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path); else next.add(path);
      return next;
    });
  };

  const selectFile = async (path: string) => {
    setSelectedFile(path);
    setPreviewLoading(true);
    setFileContent('');
    try {
      const r = await fetch(`/v1/file-content?path=${encodeURIComponent(path)}`);
      const d = await r.json();
      if (d.content !== undefined) {
        setFileContent(d.content);
        setFileSize(d.size > 10240 ? `${(d.size/1024).toFixed(1)} KB` : `${d.size} B`);
      }
    } catch { showToast('加载文件内容失败', 'error'); }
    setPreviewLoading(false);
  };

  const deleteFile = async (path: string) => {
    if (!confirm('删除此文件？将同时删除关联的 Wiki 页面。')) return;
    try {
      const r = await fetch(`/v1/sources/delete?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
      const d = await r.json();
      if (d.status === 'deleted') {
        showToast(`已删除，级联删除 ${d.wiki_pages_deleted} 个页面`, 'success');
        if (selectedFile === path) { setSelectedFile(null); setFileContent(''); }
        loadTree();
      }
    } catch { showToast('删除请求失败', 'error'); }
  };

  const extractFile = async (path: string) => {
    setPreviewLoading(true);
    setSelectedFile(path);
    try {
      const r = await fetch('/v1/sources/extract-to-wiki', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_path: path }),
      });
      const d = await r.json();
      if (d.status === 'ok') {
        showToast(`提取完成: ${d.pages_created?.length || 0} 创建`, 'success');
        loadTree();
      }
    } catch { showToast('提取请求失败', 'error'); }
    setPreviewLoading(false);
  };

  const startEdit = () => {
    setEditContent(fileContent);
    setEditing(true);
  };

  const saveEdit = async () => {
    if (!selectedFile) return;
    setSaving(true);
    try {
      const r = await fetch('/v1/sources/edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: selectedFile, content: editContent }),
      });
      const d = await r.json();
      if (d.status === 'ok') {
        setFileContent(editContent);
        showToast(d.message || '保存成功', 'success');
        setEditing(false);
        loadTree();
      } else {
        showToast(d.error || '保存失败', 'error');
      }
    } catch {
      showToast('保存请求失败', 'error');
    }
    setSaving(false);
  };

  const uploadFiles = (files: FileList | null, useRelativePath: boolean) => {
    if (!files?.length) return;
    const fd = new FormData();
    for (let i = 0; i < files.length; i++) {
      fd.append('files', files[i], useRelativePath
        ? (files[i] as any).webkitRelativePath || files[i].name
        : files[i].name);
    }
    showToast(`上传 ${files.length} 个文件...`, 'info');
    fetch('/v1/ingest/upload', { method: 'POST', body: fd })
      .then(r => r.json())
      .then(d => {
        showToast(`上传完成，${d.saved || 0} 个文件已加入队列`, 'success');
        setTimeout(loadTree, 1000);
      })
      .catch(() => showToast('上传失败', 'error'));
  };

  const renderItem = (items: SourceItem[], depth = 0): React.ReactNode => (
    <ul className="list-none p-0 m-0">
      {items.map(item => {
        if (item.type === 'directory') {
          const isOpen = expanded.has(item.path);
          const fileCount = item.children?.filter(c => c.type === 'file').length || 0;
          return (
            <li key={item.path}>
              <div
                className="flex items-center gap-1.5 px-2 py-1.5 cursor-pointer text-xs hover:bg-accent/50 rounded group transition-colors duration-100"
                style={{ paddingLeft: `${depth * 12 + 8}px` }}
                onClick={() => toggleDir(item.path)}
              >
                <span className={`text-[0.5rem] transition-transform shrink-0 ${isOpen ? 'rotate-90' : ''}`}>▶</span>
                <div className="flex items-center justify-center w-5 h-5 rounded-md bg-secondary/50 shrink-0">
                  <FolderClosed className="h-3 w-3 text-muted-foreground" />
                </div>
                <span className="flex-1 truncate">{item.name}</span>
                <span className="text-[10px] text-muted-foreground">{fileCount}</span>
              </div>
              {isOpen && item.children && renderItem(item.children, depth + 1)}
            </li>
          );
        }
        return (
          <li key={item.path}>
            <div
              className={`flex items-center gap-1.5 px-2 py-1.5 cursor-pointer text-xs rounded group transition-colors duration-100 ${
                selectedFile === item.path ? 'bg-accent text-accent-foreground' : 'hover:bg-accent/50'
              }`}
              style={{ paddingLeft: `${depth * 12 + 20}px` }}
              onClick={() => selectFile(item.path)}
            >
              <div className="flex items-center justify-center w-5 h-5 rounded-md bg-muted/50 shrink-0">
                <FileText className="h-3 w-3 text-muted-foreground shrink-0" />
              </div>
              <span className="flex-1 truncate">{item.name}</span>
              <div className="hidden group-hover:flex gap-0.5">
                <button className="text-[10px] px-1 text-muted-foreground hover:text-blue-500"
                  title="提取到 Wiki" onClick={e => { e.stopPropagation(); extractFile(item.path); }}>
                  <Sparkles className="h-3 w-3" />
                </button>
                <button className="text-[10px] px-1 text-muted-foreground hover:text-red-500"
                  title="删除" onClick={e => { e.stopPropagation(); deleteFile(item.path); }}>
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );

  const totalFiles = tree.reduce((acc, i) => acc + countFiles(i), 0);

  return (
    <>
    <div className="flex flex-1 min-h-0">
      {/* File tree sidebar */}
      <div className="w-64 flex-shrink-0 border-r border-border bg-card flex flex-col min-h-0">
        <div className="flex items-center justify-between px-3 py-2 border-b border-border">
          <span className="text-xs font-medium">原始资料</span>
          <div className="flex gap-1">
            <Button variant="ghost" size="icon" className="h-6 w-6" onClick={loadTree} title="刷新">
              <RefreshCw className="h-3 w-3" />
            </Button>
            <Button variant="default" size="icon" className="h-6 w-6" onClick={() => fileInputRef.current?.click()}>
              <Upload className="h-3 w-3" />
            </Button>
            <Button variant="outline" size="icon" className="h-6 w-6" onClick={() => folderInputRef.current?.click()}>
              <FolderClosed className="h-3 w-3" />
            </Button>
          </div>
        </div>
        <input type="file" ref={fileInputRef} className="hidden" multiple onChange={e => uploadFiles(e.target.files, false)} />
        <input type="file" ref={folderInputRef} className="hidden" multiple onChange={e => uploadFiles(e.target.files, true)} />

        <div className="flex-1 overflow-y-auto py-1">
          {loading ? (
            <div className="space-y-2 p-3">
              {[1,2,3,4].map(i => <Skeleton key={i} className="h-6 w-full" />)}
            </div>
          ) : tree.length === 0 ? (
            <div className="py-8">
              <EmptyState icon={FileText} title="暂无文件" desc="上传文件到 raw/sources/ 开始构建知识库" />
            </div>
          ) : renderItem(tree)}
        </div>

        <div className="border-t border-border p-2 text-[10px] text-muted-foreground">
          <span className="px-2">{totalFiles} 个文件</span>
          {jobs.length > 0 && (
            <div className="border-t border-border mt-1 pt-1">
              <div className="px-2 text-[10px] font-medium mb-1">任务队列</div>
              {jobs.slice(0, 3).map(j => (
                <div key={j.job_id} className="flex items-center gap-1 px-2 py-0.5 text-[10px]">
                  <span>{STATUS_ICON[j.status] || '❓'}</span>
                  <span className="flex-1 truncate">{j.source_path || j.job_id}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Content preview */}
      <div className="flex-1 flex flex-col min-h-0">
        {!selectedFile ? (
          <EmptyState icon={FileText} title="选择文件" desc="从左侧文件树中选择文件查看内容或编辑" />
        ) : previewLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <Skeleton className="h-4 w-48 mx-auto mb-2" />
              <p className="text-xs text-muted-foreground">加载中...</p>
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-4 max-w-3xl mx-auto w-full">
              <h2 className="text-lg font-bold">{selectedFile.split('/').pop()}</h2>
              <div className="flex gap-2 items-center">
                <span className="text-xs text-muted-foreground">{fileSize}</span>
                <Button size="sm" variant="outline" onClick={startEdit}>
                  <Edit3 className="h-3.5 w-3.5 mr-1" /> 编辑
                </Button>
                <Button size="sm" variant="default" onClick={() => extractFile(selectedFile!)}>
                  <Sparkles className="h-3.5 w-3.5 mr-1" /> 提取到 Wiki
                </Button>
                <Button size="sm" variant="outline" onClick={() => { setSelectedFile(null); setFileContent(''); }}>
                  关闭
                </Button>
              </div>
            </div>
            <div className="max-w-3xl mx-auto w-full">
              {selectedFile.endsWith('.md') ? (
                <MarkdownRenderer content={fileContent} />
              ) : (
                <pre className="text-xs whitespace-pre-wrap bg-muted p-4 rounded-lg">{fileContent}</pre>
              )}
            </div>
          </div>
        )}
      </div>
    </div>

    {/* ── Edit Sheet ── */}
    <Sheet open={editing} onOpenChange={(v: boolean) => { if (!v) setEditing(false); }}>
      <SheetContent className="flex flex-col w-full max-w-2xl">
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-sm font-semibold">编辑原始文件</h2>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">{selectedFile?.split('/').pop()}</span>
            <SheetClose render={<X className="h-4 w-4 cursor-pointer text-muted-foreground hover:text-foreground" />} />
          </div>
        </div>
        <div className="flex-1 p-4 min-h-0">
          <Textarea
            className="w-full h-full min-h-[300px] font-mono text-sm resize-none"
            value={editContent}
            onChange={e => setEditContent(e.target.value)}
          />
        </div>
        <div className="flex items-center justify-end gap-2 p-4 border-t border-border">
          <Button variant="outline" size="sm" onClick={() => setEditing(false)}>取消</Button>
          <Button size="sm" onClick={saveEdit} disabled={saving}>
            <Save className="h-3.5 w-3.5 mr-1" />
            {saving ? '保存中...' : '保存'}
          </Button>
        </div>
      </SheetContent>
    </Sheet>
    </>
  );
}