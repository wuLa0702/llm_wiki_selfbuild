import { useEffect, useState, useRef } from 'react';
import { renderMarkdown } from '../utils/markdown';

interface SourceFile { name: string; path: string; type: 'file' | 'directory'; children?: SourceFile[]; }

export default function SourcesContent({ defaultPath }: { defaultPath?: string | null }) {
  const [files, setFiles] = useState<SourceFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [previewLoading, setPreviewLoading] = useState(false);

  const loadFiles = () => {
    setLoading(true);
    fetch('/v1/sources/tree')
      .then(r => r.json())
      .then(d => setFiles(d.tree || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadFiles(); }, []);

  useEffect(() => {
    if (defaultPath) selectFile(defaultPath);
  }, [defaultPath]);

  const selectFile = async (path: string) => {
    setSelectedFile(path);
    setPreviewLoading(true);
    setFileContent('');
    try {
      const r = await fetch(`/v1/file-content?path=${encodeURIComponent(path)}`);
      const d = await r.json();
      if (d.content !== undefined) setFileContent(d.content);
    } catch {}
    setPreviewLoading(false);
  };

  const deleteFile = async (path: string) => {
    if (!confirm('删除此文件？')) return;
    const r = await fetch(`/v1/sources/delete?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
    const d = await r.json();
    if (d.status === 'deleted') {
      if (selectedFile === path) { setSelectedFile(null); setFileContent(''); }
      loadFiles();
    }
  };

  const flatFiles = (items: SourceFile[]): SourceFile[] => {
    const result: SourceFile[] = [];
    const walk = (items: SourceFile[]) => {
      for (const i of items) {
        if (i.type === 'file') result.push(i);
        if (i.children) walk(i.children);
      }
    };
    walk(items);
    return result;
  };

  const allFiles = flatFiles(files);

  return (
    <div className="flex-1 flex flex-col min-h-0" style={{ background: 'var(--background)' }}>
      {selectedFile ? (
        /* Preview */
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between px-5 py-2 border-b flex-shrink-0" style={{ borderColor:'var(--border)', background:'var(--surface)' }}>
            <span style={{ color:'var(--foreground)', fontSize: "var(--fs-xl)", fontWeight:500 }}>📄 {selectedFile.split('/').pop()}</span>
            <button onClick={() => { setSelectedFile(null); setFileContent(''); }}
              style={{ height: "2.25rem", background:'var(--surface-secondary)', color:'var(--muted)', border:'1px solid #333', borderRadius: "0.375rem", padding:'0 14px', fontSize: "var(--fs-sm)", cursor:'pointer', display:'inline-flex', alignItems:'center' }}>
              ✕ 关闭
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-6">
            {previewLoading ? (
              <div className="flex items-center justify-center h-full" style={{ color:'var(--muted)' }}>加载中...</div>
            ) : (
              <div className="md-content" dangerouslySetInnerHTML={{ __html: selectedFile.endsWith('.md') ? renderMarkdown(fileContent) : `<pre style="white-space:pre-wrap;font-size:14px">${fileContent}</pre>` }} />
            )}
          </div>
        </div>
      ) : (
        /* List */
        <div className="flex-1 flex flex-col min-h-0">
          {loading ? (
            <div className="flex-1 flex items-center justify-center" style={{ color:'var(--muted)' }}>加载中...</div>
          ) : allFiles.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center" style={{ color:'var(--muted)', gap: "0.5rem" }}>
              <div style={{ fontSize: "2.5rem", opacity:0.3, marginBottom: "0.25rem" }}>📂</div>
              <div style={{ color:'var(--default-foreground)', fontSize: "var(--fs-lg)", fontWeight:500 }}>暂无资料</div>
              <div style={{ fontSize: "var(--fs-sm)" }}>导入文档，开始构建你的Wiki</div>
              <div className="flex gap-3" style={{ marginTop: "var(--fs-sm)" }}>
                <button style={{ height: "2.25rem", background:'transparent', color:'var(--default-foreground)', border:'1px solid #555', borderRadius: "0.375rem", padding:'0 20px', fontSize: "var(--fs-md)", cursor:'pointer', display:'inline-flex', alignItems:'center' }}>导入文件</button>
                <button style={{ height: "2.25rem", background:'transparent', color:'var(--default-foreground)', border:'1px solid #555', borderRadius: "0.375rem", padding:'0 20px', fontSize: "var(--fs-md)", cursor:'pointer', display:'inline-flex', alignItems:'center' }}>文件夹</button>
              </div>
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto px-5 py-3">
              {allFiles.map(f => (
                <div key={f.path}
                  className="flex items-center gap-3 px-3 py-2.5 rounded cursor-pointer group"
                  style={{ borderBottom: '1px solid #2A2A2A' }}
                  onClick={() => selectFile(f.path)}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-tertiary)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <span style={{ fontSize: "var(--fs-md)" }}>📄</span>
                  <span className="flex-1 truncate" style={{ color:'var(--default-foreground)', fontSize: "var(--fs-md)" }}>{f.name}</span>
                  <span className="hidden group-hover:flex gap-3">
                    <button onClick={e => { e.stopPropagation(); selectFile(f.path); }}
                      style={{ background:'none', border:'none', color:'var(--muted)', fontSize: "var(--fs-sm)", cursor:'pointer' }}>👁 预览阅读</button>
                    <button onClick={e => { e.stopPropagation(); deleteFile(f.path); }}
                      style={{ background:'none', border:'none', color:'var(--muted)', fontSize: "var(--fs-sm)", cursor:'pointer' }}>🗑 删除</button>
                  </span>
                </div>
              ))}
            </div>
          )}
          {!selectedFile && (
            <div className="flex items-center justify-end gap-3 px-5 border-t flex-shrink-0" style={{ height: "2.625rem", borderColor:'var(--border)' }}>
              <span style={{ color:'var(--muted)', fontSize: "var(--fs-sm)" }}>{allFiles.length} 个资料</span>
              <button onClick={loadFiles}
                style={{ background:'none', border:'none', color:'var(--muted)', fontSize: "var(--fs-sm)", cursor:'pointer', display:'inline-flex', alignItems:'center', gap: "0.25rem" }}>
                🔄 刷新文件夹
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
