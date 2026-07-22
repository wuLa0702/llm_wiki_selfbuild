import { useEffect, useState, useRef } from 'react';
import { FileText, FolderClosed, Upload, Trash2, RefreshCw, Sparkles, Edit3, Save, X, ChevronDown, ChevronRight, RotateCcw, AlertCircle, CheckCircle2, Clock, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { Sheet, SheetContent, SheetClose } from '@/components/ui/sheet';
import { showToast } from '@/components/shared/Toast';
import MarkdownRenderer from '@/components/shared/MarkdownRenderer';
import EmptyState from '@/components/shared/EmptyState';

/* ─── Types ─── */

interface SourceItem {
  name: string; type: 'file' | 'directory'; path: string;
  size?: number; children?: SourceItem[];
}

interface QueueJob {
  job_id: string; source_path: string; status: string;
  error?: string; result_summary?: string;
}

interface QueueProgress {
  total: number; pending: number; processing: number;
  done: number; failed: number; cancelled: number;
}

/* ─── Helpers ─── */

const STATUS_CONFIG: Record<string, { icon: typeof Clock; color: string; label: string }> = {
  pending:    { icon: Clock,     color: 'text-muted-foreground', label: '等待中' },
  processing: { icon: Loader2,   color: 'text-blue-500',        label: '处理中' },
  done:       { icon: CheckCircle2, color: 'text-green-500',    label: '完成' },
  failed:     { icon: AlertCircle,  color: 'text-red-500',      label: '失败' },
  cancelled:  { icon: X,          color: 'text-muted-foreground/50', label: '已取消' },
};

function countFiles(item: SourceItem): number {
  if (item.type === 'file') return 1;
  return (item.children || []).reduce((acc, c) => acc + countFiles(c), 0);
}

/* ─── Queue Panel Component ─── */

function QueuePanel({
  jobs, progress, collapsed, onToggle, onRetry, onClearFailed,
}: {
  jobs: QueueJob[]; progress: QueueProgress | null;
  collapsed: boolean; onToggle: () => void;
  onRetry: (jobId: string) => void; onClearFailed: () => void;
}) {
  const activeJobs = jobs.filter(j => j.status === 'pending' || j.status === 'processing');
  const failedJobs = jobs.filter(j => j.status === 'failed');
  const doneCount = progress?.done ?? jobs.filter(j => j.status === 'done').length;
  const total = progress?.total ?? jobs.length;
  const pct = total > 0 ? Math.round(((doneCount + (progress?.failed ?? 0) + (progress?.cancelled ?? 0)) / total) * 100) : 0;

  if (jobs.length === 0) return null;

  return (
    <div className="border-t border-border">
      {/* Header — clickable toggle */}
      <button
        className="flex items-center justify-between w-full px-3 py-2 text-[10px] font-medium text-muted-foreground hover:text-foreground hover:bg-accent/30 transition-colors cursor-pointer"
        onClick={onToggle}
      >
        <div className="flex items-center gap-1.5">
          {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
          <span>导入队列</span>
          {activeJobs.length > 0 && (
            <Badge variant="default" className="text-[9px] h-4 px-1 bg-blue-500 text-white">
              {activeJobs.length} 活跃
            </Badge>
          )}
          {failedJobs.length > 0 && (
            <Badge variant="outline" className="text-[9px] h-4 px-1 text-red-500 border-red-300">
              {failedJobs.length} 失败
            </Badge>
          )}
        </div>
        <span className="text-[9px] text-muted-foreground/50">{doneCount}/{total}</span>
      </button>

      {!collapsed && (
        <div className="px-3 pb-2 space-y-2">
          {/* Progress bar */}
          {total > 0 && (
            <div className="space-y-1">
              <div className="flex items-center justify-between text-[9px] text-muted-foreground/60">
                <span>{pct}%</span>
                <span className="flex items-center gap-1">
                  {progress && (
                    <>
                      <span className="text-blue-500">{progress.processing} 处理中</span>
                      <span>·</span>
                      <span className="text-green-500">{progress.done} 完成</span>
                      {progress.failed > 0 && <><span>·</span><span className="text-red-500">{progress.failed} 失败</span></>}
                    </>
                  )}
                </span>
              </div>
              <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                {progress && (
                  <div className="flex h-full rounded-full overflow-hidden">
                    <div
                      className="bg-green-500 transition-all duration-500"
                      style={{ width: `${(progress.done / total) * 100}%` }}
                    />
                    <div
                      className="bg-red-500 transition-all duration-500"
                      style={{ width: `${(progress.failed / total) * 100}%` }}
                    />
                    <div
                      className="bg-blue-400 animate-pulse transition-all duration-500"
                      style={{ width: `${(progress.processing / total) * 100}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Job list */}
          <div className="max-h-[200px] overflow-y-auto space-y-0.5">
            {jobs.slice(0, 15).map(job => {
              const cfg = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;
              const Icon = cfg.icon;
              return (
                <div
                  key={job.job_id}
                  className="flex items-center gap-1.5 px-1.5 py-1 rounded text-[10px] hover:bg-muted/50 transition-colors group"
                >
                  <Icon className={`h-3 w-3 shrink-0 ${cfg.color} ${job.status === 'processing' ? 'animate-spin' : ''}`} />
                  <span className="flex-1 truncate" title={job.source_path}>
                    {job.source_path || job.job_id}
                  </span>
                  <span className="text-[9px] text-muted-foreground/40 shrink-0">{cfg.label}</span>
                  {job.status === 'failed' && (
                    <button
                      className="opacity-0 group-hover:opacity-100 text-[9px] px-1 py-0.5 rounded text-red-500 hover:bg-red-500/10 transition-all cursor-pointer shrink-0"
                      onClick={() => onRetry(job.job_id)}
                      title="重试"
                    >
                      <RotateCcw className="h-2.5 w-2.5" />
                    </button>
                  )}
                </div>
              );
            })}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            {failedJobs.length > 1 && (
              <Button
                variant="ghost"
                size="sm"
                className="h-5 text-[9px] gap-1 px-1.5 text-red-500 hover:text-red-600 hover:bg-red-500/10"
                onClick={onClearFailed}
              >
                <Trash2 className="h-2.5 w-2.5" />
                清空失败记录
              </Button>
            )}
            {failedJobs.length > 0 && (
              <Button
                variant="ghost"
                size="sm"
                className="h-5 text-[9px] gap-1 px-1.5"
                onClick={() => failedJobs.forEach(j => onRetry(j.job_id))}
              >
                <RotateCcw className="h-2.5 w-2.5" />
                全部重试
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Main Page ─── */

export default function SourcesPage() {
  const [tree, setTree] = useState<SourceItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [fileSize, setFileSize] = useState('');
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [jobs, setJobs] = useState<QueueJob[]>([]);
  const [queueProgress, setQueueProgress] = useState<QueueProgress | null>(null);
  const [queueCollapsed, setQueueCollapsed] = useState(false);
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

  /* ─── Queue polling ─── */
  useEffect(() => {
    const fetchQueue = () => {
      Promise.all([
        fetch('/v1/ingest/queue/recent?limit=15').then(r => r.json()),
        fetch('/v1/ingest/queue/status').then(r => r.json()),
      ]).then(([recent, status]) => {
        setJobs(recent.jobs || []);
        setQueueProgress(status);
      }).catch(() => {});
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

  const extractFile = async (path: string, force = false) => {
    setPreviewLoading(true);
    setSelectedFile(path);

    // 预检：检查文件自上次 ingest 后是否有变化
    if (!force) {
      try {
        const check = await fetch(`/v1/sources/check-changed?path=${encodeURIComponent(path)}`);
        const d = await check.json();
        if (d.changed === false) {
          setPreviewLoading(false);
          const ok = window.confirm(
            '该文件内容自上次生成 Wiki 后没有变化。\n\n' +
            '· 点击「确定」强制重新生成（消耗 LLM 额度）\n' +
            '· 点击「取消」跳过本次操作'
          );
          if (!ok) return;
          // 用户确认强制生成 → 带 force=true 重新调用
          return extractFile(path, true);
        }
      } catch {
        // 预检失败降级容忍：继续执行提取
      }
    }

    try {
      const r = await fetch('/v1/sources/extract-to-wiki', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_path: path, force }),
      });
      const d = await r.json();
      if (d.status === 'skipped') {
        showToast('文件内容无变化，已跳过。勾选"强制生成"可重新提取。', 'info');
      } else if (d.status === 'ok' || d.status === 'success') {
        const created = d.pages_created?.length || 0;
        const updated = d.pages_updated?.length || 0;
        const parts = [];
        if (created) parts.push(`${created} 创建`);
        if (updated) parts.push(`${updated} 更新`);
        showToast(`提取完成：${parts.join(' · ') || '无变更'}`, 'success');
        loadTree();
      } else if (d.error) {
        showToast(`提取失败：${d.error}`, 'error');
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

  const retryJob = async (jobId: string) => {
    try {
      const r = await fetch(`/v1/ingest/queue/retry/${jobId}`, { method: 'POST' });
      const d = await r.json();
      if (d.status === 'ok') showToast('已重新加入队列', 'success');
    } catch { showToast('重试请求失败', 'error'); }
  };

  const clearFailed = async () => {
    try {
      const r = await fetch('/v1/ingest/queue/failed', { method: 'DELETE' });
      const d = await r.json();
      showToast(`已清理 ${d.deleted || 0} 条失败记录`, 'success');
    } catch { showToast('清理请求失败', 'error'); }
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
    <div className="flex flex-1 min-h-0 overflow-hidden">
      {/* File tree sidebar */}
      <div className="w-64 flex-shrink-0 border-r border-border bg-card flex flex-col min-h-0 overflow-hidden">
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

        <div className="flex-1 overflow-y-scroll py-1">
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

        {/* ── Queue Panel (sidebar footer) ── */}
        <QueuePanel
          jobs={jobs}
          progress={queueProgress}
          collapsed={queueCollapsed}
          onToggle={() => setQueueCollapsed(v => !v)}
          onRetry={retryJob}
          onClearFailed={clearFailed}
        />

        <div className="border-t border-border px-3 py-1.5 text-[10px] text-muted-foreground">
          {totalFiles} 个文件
        </div>
      </div>

      {/* Content preview */}
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
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
          <div className="flex-1 overflow-y-scroll p-6">
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
