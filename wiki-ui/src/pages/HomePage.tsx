import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import MidPanel from '../components/MidPanel';
import SourcesContent from '../components/SourcesContent';

export default function HomePage() {
  const navigate = useNavigate();
  const [selectedPage, setSelectedPage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const handleSelectPage = (path: string) => {
    navigate(`/wiki?path=${encodeURIComponent(path)}`);
  };

  const uploadFiles = (files: FileList | null, useRelativePath: boolean) => {
    if (!files?.length) return;
    const fd = new FormData();
    for (let i = 0; i < files.length; i++) {
      fd.append('files', files[i], useRelativePath ? (files[i] as any).webkitRelativePath || files[i].name : files[i].name);
    }
    fetch('/v1/ingest/upload', { method: 'POST', body: fd }).catch(() => {});
  };

  return (
    <div className="flex flex-1 min-h-0">
      <MidPanel onSelectPage={handleSelectPage} onTabChange={() => setSelectedPage(null)} />
      <div className="flex-1 flex flex-col min-h-0">
        {/* Persistent top toolbar */}
        <div
          className="flex items-center justify-between px-5 py-3 border-b flex-shrink-0"
          style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
        >
          <span style={{ color: 'var(--foreground)', fontSize: "var(--fs-xl)", fontWeight: 600 }}>原始资料</span>
          <div className="flex items-center gap-3">
            <button
              onClick={() => window.location.reload()}
              style={{ height: "2.25rem", width: "2.25rem", background: 'none', border: 'none', color: 'var(--muted)', fontSize: "var(--fs-lg)", cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}
              title="刷新文件夹"
            >
              🔄
            </button>
            <button
              onClick={() => fileInputRef.current?.click()}
              style={{ height: "2.25rem", background: 'var(--surface-secondary)', color: '#FFF', border: 'none', borderRadius: "0.375rem", padding: '0 14px', fontSize: "var(--fs-md)", cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: "0.25rem" }}
            >
              <span style={{ fontSize: "var(--fs-lg)", fontWeight: 700 }}>+</span> 导入
            </button>
            <button
              onClick={() => folderInputRef.current?.click()}
              style={{ height: "2.25rem", background: 'var(--surface-secondary)', color: '#FFF', border: 'none', borderRadius: "0.375rem", padding: '0 14px', fontSize: "var(--fs-md)", cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: "0.25rem" }}
            >
              <span style={{ fontSize: "var(--fs-lg)", fontWeight: 700 }}>+</span> 文件夹
            </button>
          </div>
        </div>

        {/* Content area — unified SourcesContent for both tabs */}
        <div className="flex-1 flex min-h-0">
          <SourcesContent defaultPath={selectedPage} />
        </div>
      </div>

      <input type="file" ref={fileInputRef} className="hidden" multiple onChange={e => uploadFiles(e.target.files, false)} />
      <input type="file" ref={folderInputRef} className="hidden" multiple webkitdirectory="true" onChange={e => uploadFiles(e.target.files, true)} />
    </div>
  );
}
