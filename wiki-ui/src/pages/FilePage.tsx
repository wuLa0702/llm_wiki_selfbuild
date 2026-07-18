import { useEffect, useState, useRef } from 'react';
import { renderMarkdown } from '../utils/markdown';

export default function FilePage() {
  const [files, setFiles] = useState<{name:string;path:string}[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [content, setContent] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement>(null);

  const loadFiles = () => {
    fetch('/v1/sources/tree').then(r => r.json()).then(d => {
      const flat: {name:string;path:string}[] = [];
      const walk = (items: any[]) => {
        for (const i of items) {
          if (i.type === 'file') flat.push({ name: i.name, path: i.path });
          if (i.children) walk(i.children);
        }
      };
      walk(d.tree || []);
      setFiles(flat);
    }).catch(() => {});
  };

  useEffect(() => { loadFiles(); }, []);

  const selectFile = async (path: string) => {
    setSelected(path);
    try {
      const r = await fetch(`/v1/file-content?path=${encodeURIComponent(path)}`);
      const d = await r.json();
      if (d.content !== undefined) setContent(d.content);
    } catch {}
  };

  const deleteFile = async (path: string) => {
    if (!confirm('删除此文件？')) return;
    const r = await fetch(`/v1/sources/delete?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
    const d = await r.json();
    if (d.status === 'deleted') { setSelected(null); setContent(''); loadFiles(); }
  };

  return (
    <div className="flex flex-1 min-h-0">
      <div style={{ width: 320, background: 'var(--surface)', borderRight: '1px solid #333', display: 'flex', flexDirection: 'column' }}>
        <div className="flex items-center justify-between px-3 py-2 border-b" style={{ borderColor: 'var(--border)' }}>
          <span style={{ color: '#FFF', fontSize: 13, fontWeight: 600 }}>原始资料</span>
          <div className="flex gap-1">
            <button onClick={loadFiles} style={{ background:'var(--surface-secondary)', color:'var(--muted)', border:'none', cursor:'pointer', padding:'2px 6px', borderRadius:4, fontSize:11 }}>🔄</button>
            <button onClick={() => fileRef.current?.click()} style={{ background:'var(--accent)', color:'#FFF', border:'none', cursor:'pointer', padding:'2px 6px', borderRadius:4, fontSize:11 }}>+导入</button>
            <button onClick={() => folderRef.current?.click()} style={{ background:'var(--surface-secondary)', color:'var(--muted)', border:'none', cursor:'pointer', padding:'2px 6px', borderRadius:4, fontSize:11 }}>+文件夹</button>
          </div>
        </div>
        <input type="file" ref={fileRef} className="hidden" multiple onChange={e => { /* upload */ }} />
        <input type="file" ref={folderRef} className="hidden" multiple webkitdirectory="true" onChange={e => { /* upload folder */ }} />

        <div className="flex-1 overflow-y-auto">
          {files.map(f => (
            <div key={f.path}
              className="flex items-center gap-2 px-3 py-2 cursor-pointer text-sm group"
              style={{ color: selected === f.path ? '#FFF' : 'var(--default-foreground)', background: selected === f.path ? 'var(--surface-tertiary)' : 'transparent' }}
              onClick={() => selectFile(f.path)}
              onMouseEnter={e => { if (selected !== f.path) e.currentTarget.style.background = 'var(--surface-tertiary)'; }}
              onMouseLeave={e => { if (selected !== f.path) e.currentTarget.style.background = 'transparent'; }}
            >
              <span>📄</span>
              <span className="flex-1 truncate">{f.name}</span>
              <span className="hidden group-hover:flex gap-1">
                <button onClick={e => { e.stopPropagation(); deleteFile(f.path); }} style={{ background:'none', border:'none', color:'var(--danger)', cursor:'pointer', fontSize:11 }}>🗑</button>
              </span>
            </div>
          ))}
        </div>
        <div className="px-3 py-2 border-t text-xs" style={{ borderColor:'var(--border)', color:'var(--muted)' }}>{files.length} 个资料</div>
      </div>

      <div className="flex-1 flex flex-col" style={{ background: 'var(--background)' }}>
        {!selected ? (
          <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--muted)' }}>
            <div className="text-center"><div style={{fontSize:32,opacity:0.4,marginBottom:8}}>📂</div><p style={{fontSize:14}}>Select a file to preview</p></div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-6">
            <h2 style={{color:'#FFF',fontSize:18,marginBottom:16}}>{selected.split('/').pop()}</h2>
            <div dangerouslySetInnerHTML={{__html: selected.endsWith('.md') ? renderMarkdown(content) : `<pre style="white-space:pre-wrap;font-size:13px">${content}</pre>`}} />
          </div>
        )}
      </div>
    </div>
  );
}
