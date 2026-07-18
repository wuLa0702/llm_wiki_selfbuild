import { useEffect, useState, useRef } from 'react';
import { renderMarkdown } from '../utils/markdown';
import { showToast } from '../components/Toast';

interface SourceItem {
  name: string;
  type: 'file' | 'directory';
  path: string;
  size?: number;
  children?: SourceItem[];
}

interface QueueJob {
  job_id: string;
  source_path: string;
  status: string;
  error?: string;
  result_summary?: string;
}

const STATUS_ICON: Record<string, string> = {
  pending: '⏳', processing: '🔄', done: '✅', failed: '❌',
};

export default function SourcesPage() {
  const [tree, setTree] = useState<SourceItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [fileSize, setFileSize] = useState('');
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [jobs, setJobs] = useState<QueueJob[]>([]);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
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
      if (next.has(path)) next.delete(path);
      else next.add(path);
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
      } else {
        showToast(`删除失败: ${d.error || '未知错误'}`, 'error');
      }
    } catch { showToast('删除请求失败', 'error'); }
  };

  const deleteFolder = async (path: string) => {
    if (!confirm('确定删除此文件夹及其所有子文件？')) return;
    try {
      const r = await fetch(`/v1/sources/folder/${encodeURIComponent(path)}`, { method: 'DELETE' });
      const d = await r.json();
      if (d.status === 'deleted') {
        showToast(`已删除文件夹及 ${d.wiki_pages_deleted} 个关联页面`, 'success');
        loadTree();
      } else {
        showToast(`删除失败: ${d.error || '未知错误'}`, 'error');
      }
    } catch { showToast('删除请求失败', 'error'); }
  };

  const uploadFiles = (files: FileList | null, useRelativePath: boolean) => {
    if (!files?.length) return;
    const btn = useRelativePath
      ? folderInputRef.current?.previousElementSibling
      : fileInputRef.current?.previousElementSibling;
    const fd = new FormData();
    for (let i = 0; i < files.length; i++) {
      fd.append('files', files[i], useRelativePath ? (files[i] as any).webkitRelativePath || files[i].name : files[i].name);
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
        showToast(`提取完成: ${d.pages_created?.length || 0} 创建, ${d.pages_updated?.length || 0} 更新`, 'success');
        loadTree();
      } else {
        showToast(`提取失败: ${d.error || ''}`, 'error');
      }
    } catch { showToast('提取请求失败', 'error'); }
    setPreviewLoading(false);
  };

  const renderTree = (items: SourceItem[], depth = 0) => (
    <ul className="list-none p-0 m-0">
      {items.map(item => {
        if (item.type === 'directory') {
          const isOpen = expanded.has(item.path);
          const fileCount = item.children?.filter(c => c.type === 'file').length || 0;
          return (
            <li key={item.path}>
              <div
                className="flex items-center gap-1 px-2 py-1 cursor-pointer text-xs text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-neutral-800 group"
                style={{ paddingLeft: `${depth * 12 + 8}px` }}
                onClick={() => toggleDir(item.path)}
              >
                <span className={`text-[0.5rem] transition-transform ${isOpen ? 'rotate-90' : ''}`}>▶</span>
                <span>📁</span>
                <span className="flex-1 truncate">{item.name}</span>
                <span className="text-[9px] text-gray-400">{fileCount}</span>
                <button
                  className="hidden group-hover:block text-[9px] px-1 text-gray-400 hover:text-red-500"
                  title="删除文件夹"
                  onClick={e => { e.stopPropagation(); deleteFolder(item.path); }}
                >
                  🗑
                </button>
              </div>
              {isOpen && item.children && renderTree(item.children, depth + 1)}
            </li>
          );
        }
        return (
          <li key={item.path}>
            <div
              className={`flex items-center gap-1 px-2 py-1 cursor-pointer text-xs group hover:bg-gray-50 dark:hover:bg-neutral-800 rounded ${
                selectedFile === item.path ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600' : 'text-gray-600 dark:text-gray-400'
              }`}
              style={{ paddingLeft: `${depth * 12 + 8}px` }}
              onClick={() => selectFile(item.path)}
            >
              <span className="w-3">📄</span>
              <span className="flex-1 truncate">{item.name}</span>
              <span className="hidden group-hover:flex gap-0.5">
                <button
                  className="text-[9px] px-1 text-gray-400 hover:text-blue-500"
                  title="提取到 Wiki"
                  onClick={e => { e.stopPropagation(); extractFile(item.path); }}
                >
                  ✨
                </button>
                <button
                  className="text-[9px] px-1 text-gray-400 hover:text-red-500"
                  title="删除"
                  onClick={e => { e.stopPropagation(); deleteFile(item.path); }}
                >
                  🗑
                </button>
              </span>
            </div>
          </li>
        );
      })}
    </ul>
  );

  return (
    <div className="flex flex-1 min-h-0">
      <aside className="w-60 flex-shrink-0 bg-gray-50 dark:bg-neutral-900 border-r border-gray-200 dark:border-neutral-700 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-neutral-700">
          <span className="text-xs font-medium text-gray-700 dark:text-gray-300">原始资料</span>
          <div className="flex gap-1">
            <button className="text-[10px] px-1.5 py-0.5 rounded bg-gray-200 dark:bg-neutral-700 text-gray-600 dark:text-gray-300 hover:bg-gray-300" onClick={loadTree} title="刷新">🔄</button>
            <button className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500 text-white hover:bg-blue-600" onClick={() => fileInputRef.current?.click()}>+导入</button>
            <button className="text-[10px] px-1.5 py-0.5 rounded bg-gray-200 dark:bg-neutral-700 text-gray-600 dark:text-gray-300 hover:bg-gray-300" onClick={() => folderInputRef.current?.click()}>+文件夹</button>
          </div>
        </div>
        <input type="file" ref={fileInputRef} className="hidden" multiple onChange={e => uploadFiles(e.target.files, false)} />
        <input type="file" ref={folderInputRef} className="hidden" multiple webkitdirectory="true" onChange={e => uploadFiles(e.target.files, true)} />

        <div className="flex-1 overflow-y-auto py-1">
          {loading ? (
            <div className="flex items-center justify-center py-8 text-gray-400">
              <div className="animate-spin text-sm mr-2">⏳</div>
              <span className="text-xs">加载中...</span>
            </div>
          ) : tree.length === 0 ? (
            <div className="text-xs text-gray-400 text-center py-8">
              <div className="text-2xl mb-2 opacity-30">📂</div>
              暂无文件
            </div>
          ) : renderTree(tree)}
        </div>

        <div className="border-t border-gray-200 dark:border-neutral-700">
          <div className="flex items-center justify-between px-3 py-1 text-[10px] text-gray-400">
            <span>共 {tree.reduce((acc, i) => acc + countFiles(i), 0)} 个文件</span>
          </div>
          <div className="border-t border-gray-100 dark:border-neutral-800">
            <div className="px-3 py-1 text-[10px] font-medium text-gray-500">任务队列</div>
            {jobs.length === 0 ? (
              <div className="text-[10px] text-gray-400 text-center py-1">暂无</div>
            ) : (
              jobs.slice(0, 5).map(j => (
                <div key={j.job_id} className="flex items-center gap-1 px-3 py-0.5 text-[10px] text-gray-500">
                  <span>{STATUS_ICON[j.status] || '❓'}</span>
                  <span className="flex-1 truncate">{j.source_path || j.job_id}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </aside>

      <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
        {!selectedFile ? (
          <div className="flex-1 flex items-center justify-center text-gray-400 dark:text-gray-500">
            <div className="text-center">
              <div className="text-3xl mb-2 opacity-30">📂</div>
              <p className="text-sm">从左侧选择文件查看</p>
            </div>
          </div>
        ) : previewLoading ? (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            <div className="text-center">
              <div className="animate-spin text-lg mb-2">⏳</div>
              <p className="text-sm">加载中...</p>
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold m-0">{selectedFile.split('/').pop()}</h2>
              <div className="flex gap-2 items-center">
                <span className="text-[10px] text-gray-400">{fileSize}</span>
                <button
                  className="text-xs px-2 py-1 rounded bg-blue-500 text-white hover:bg-blue-600"
                  onClick={() => extractFile(selectedFile)}
                >
                  ✨ 提取到 Wiki
                </button>
                <button
                  className="text-xs px-2 py-1 rounded text-gray-500 hover:text-red-500"
                  onClick={() => { setSelectedFile(null); setFileContent(''); }}
                >
                  ✕ 关闭
                </button>
              </div>
            </div>
            <div
              className="max-w-none"
              dangerouslySetInnerHTML={{
                __html: selectedFile.endsWith('.md')
                  ? renderMarkdown(fileContent)
                  : `<pre class="text-xs whitespace-pre-wrap bg-gray-50 dark:bg-neutral-800 p-4 rounded">${escapeHtml(fileContent)}</pre>`,
              }}
            />
          </div>
        )}
      </div>
    </div>
  );
}

function countFiles(item: SourceItem): number {
  if (item.type === 'file') return 1;
  return (item.children || []).reduce((acc, c) => acc + countFiles(c), 0);
}

function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
