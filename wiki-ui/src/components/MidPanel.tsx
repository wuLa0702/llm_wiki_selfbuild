import { useEffect, useState } from 'react';

interface FileNode { type: 'file' | 'directory'; size?: number; children?: Record<string, FileNode>; }
interface QueueJob { job_id: string; source_path: string; status: string; error?: string; result_summary?: string; }

export default function MidPanel({ onSelectPage, onTabChange }: { onSelectPage: (path: string) => void; onTabChange?: (tab: 'wiki' | 'raw') => void }) {
  const [tab, setTab] = useState<'wiki' | 'raw'>('wiki');
  const [wikiTree, setWikiTree] = useState<Record<string, FileNode>>({});
  const [rawTree, setRawTree] = useState<Record<string, FileNode>>({});
  const [jobs, setJobs] = useState<QueueJob[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [queueOpen, setQueueOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);

  useEffect(() => {
    fetch('/v1/file-tree')
      .then(r => r.json())
      .then(d => {
        setWikiTree(d.wiki?.children || {});
        setRawTree(d.raw?.children || {});
      })
      .catch(() => {})
      .finally(() => setLoading(false));

    const poll = () => {
      fetch('/v1/ingest/queue/recent?limit=20')
        .then(r => r.json())
        .then(d => setJobs(d.jobs || []))
        .catch(() => {});
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, []);

  const retryJob = (jobId: string) => {
    fetch(`/v1/ingest/queue/retry/${jobId}`, { method: 'POST' }).catch(() => {});
  };
  const deleteJob = (jobId: string) => {
    fetch(`/v1/ingest/queue/${jobId}`, { method: 'DELETE' }).catch(() => {});
  };
  const retryAll = () => {
    const failed = jobs.filter(j => j.status === 'failed');
    failed.forEach(j => retryJob(j.job_id));
  };
  const deleteAllFailed = () => {
    fetch('/v1/ingest/queue/failed', { method: 'DELETE' }).catch(() => {});
  };
  const clearAllRecords = () => {
    fetch('/v1/ingest/queue/all', { method: 'DELETE' })
      .then(r => r.json())
      .then(d => { if (d.status === 'ok') setJobs([]); })
      .catch(() => {});
  };

  const toggleExpand = (path: string) => setExpanded(prev => ({ ...prev, [path]: !prev[path] }));

  const countFiles = (children: Record<string, FileNode>): number =>
    Object.values(children).reduce((acc, n) => acc + (n.type === 'file' ? 1 : countFiles(n.children || {})), 0);

  const renderTree = (children: Record<string, FileNode>, prefix = ''): JSX.Element => {
    const entries = Object.entries(children);
    if (!entries.length) return <></>;
    return (
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {entries.map(([name, node]) => {
          const fullPath = prefix ? `${prefix}/${name}` : name;
          if (node.type === 'directory') {
            const isOpen = expanded[fullPath];
            return (
              <li key={fullPath}>
                <div className="flex items-center gap-1.5 px-3 py-1.5 cursor-pointer" style={{ color: 'var(--muted)', fontSize: "var(--fs-md)" }}
                  onClick={() => toggleExpand(fullPath)}
                  onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-tertiary)'}
                  onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                >
                  <span style={{ fontSize: "0.625rem", transition: 'transform 0.15s', transform: isOpen ? 'rotate(90deg)' : 'none' }}>▶</span>
                  <span>📁</span>
                  <span className="truncate flex-1">{name}</span>
                  <span style={{ color: 'var(--muted)', fontSize: "var(--fs-xs)" }}>{countFiles(node.children || {})}</span>
                </div>
                {isOpen && node.children && <div style={{ paddingLeft: "0.5rem" }}>{renderTree(node.children, fullPath)}</div>}
              </li>
            );
          }
          return (
            <li key={fullPath}>
              <div className="flex items-center gap-1.5 px-3 py-1.5 cursor-pointer" style={{ color: 'var(--default-foreground)', fontSize: "var(--fs-md)", paddingLeft: prefix ? 40 : 8 }}
                onClick={() => onSelectPage(fullPath)}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-tertiary)'}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <span>📄</span>
                <span className="truncate">{name}</span>
              </div>
            </li>
          );
        })}
      </ul>
    );
  };

  const failedCount = jobs.filter(j => j.status === 'failed').length;
  const doneCount = jobs.filter(j => j.status === 'done').length;
  const pendingCount = jobs.filter(j => j.status === 'pending' || j.status === 'processing').length;
  const totalJobs = jobs.length;

  return (
    <aside className="flex-shrink-0 flex flex-col border-r" style={{ width: "20rem", background: 'var(--surface)', borderColor: 'var(--border)' }}>
      {/* Tabs */}
      <div className="flex border-b" style={{ borderColor: 'var(--border)' }}>
        {(['wiki', 'raw'] as const).map(t => (
          <button key={t}
            className="flex-1 py-3 font-medium transition-colors"
            style={{ fontSize: "var(--fs-md)", color: tab === t ? 'var(--foreground)' : 'var(--muted)', borderBottom: tab === t ? '2px solid #3684FF' : '2px solid transparent', background: 'none', cursor: 'pointer', borderTop: 'none', borderLeft: 'none', borderRight: 'none' }}
            onClick={() => { setTab(t); onTabChange?.(t); }}
          >
            {t === 'wiki' ? '📚 知识库' : '📁 文件'}
          </button>
        ))}
      </div>

      {/* Tree */}
      <div className="flex-1 overflow-y-auto" style={{ padding: '4px 0' }}>
        {loading ? (
          <div style={{ color: 'var(--muted)', fontSize: "var(--fs-md)", textAlign: 'center', padding: "1.5rem" }}>⏳ 正在加载...</div>
        ) : tab === 'wiki' ? (
          Object.keys(wikiTree).length === 0 ? (
            <div style={{ color: 'var(--muted)', fontSize: "var(--fs-md)", textAlign: 'center', padding: '48px 16px', lineHeight: "2px" }}>
              <div style={{ fontSize: "2.25rem", marginBottom: "var(--fs-sm)", opacity: 0.3 }}>📚</div>
              <div style={{ color: 'var(--default-foreground)', fontSize: "var(--fs-md)" }}>知识库还没有内容</div>
              <div style={{ fontSize: "var(--fs-sm)", marginTop: "2px" }}>点击右上角「导入」按钮，添加你的第一篇文档吧 ✨</div>
            </div>
          ) : renderTree(wikiTree, 'wiki')
        ) : (
          Object.keys(rawTree).length === 0 ? (
            <div style={{ color: 'var(--muted)', fontSize: "var(--fs-md)", textAlign: 'center', padding: "1.5rem" }}>暂无文件</div>
          ) : renderTree(rawTree, 'raw')
        )}
      </div>

      {/* Queue panel — drawer at bottom (always visible) */}
      <div className="relative" style={{ borderTop: !queueOpen ? '1px solid #333' : 'none' }}>
        {/* Pull tab — always visible when collapsed */}
        {!queueOpen && (
          <div
            className="flex items-center justify-center cursor-pointer"
            style={{ height: "2.625rem", background: 'var(--surface)' }}
            onClick={() => setQueueOpen(true)}
            onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-tertiary)'}
            onMouseLeave={e => e.currentTarget.style.background = 'var(--surface)'}
          >
            <span style={{ fontSize: "var(--fs-xs)", color: 'var(--muted)', display:'flex', alignItems:'center', gap: "0.25rem" }}>
              {failedCount > 0 ? (
                <span style={{ color:'var(--danger)', fontSize: "var(--fs-xs)" }}>{failedCount} failed</span>
              ) : pendingCount > 0 ? (
                <span style={{ color:'var(--accent)' }}>{pendingCount} 处理中</span>
              ) : totalJobs > 0 ? (
                <span style={{ color:'var(--success)' }}>{doneCount} 完成</span>
              ) : (
                <span style={{ color:'var(--muted)' }}>📋 导入队列 · 空闲中</span>
              )}
              <span>▲</span>
            </span>
          </div>
        )}

        {/* Drawer content */}
        {queueOpen && (
          <div>
            {/* Header row */}
            <div className="flex items-center justify-between px-3 py-2" style={{ background: failedCount > 0 ? 'var(--surface-tertiary)' : 'var(--surface)', borderBottom: '1px solid #2A2A2A' }}>
              <div className="flex items-center gap-2">
                <span style={{ color: failedCount > 0 ? 'var(--danger)' : 'var(--default-foreground)', fontSize: "var(--fs-sm)", fontWeight: 500 }}>导入队列</span>
                <span style={{ color: 'var(--muted)', fontSize: "var(--fs-sm)" }}>
                  {doneCount}成功 {failedCount}失败 {pendingCount > 0 ? `${pendingCount}处理中` : ''}
                </span>
              </div>
              <button onClick={e => { e.stopPropagation(); clearAllRecords(); }}
                style={{ background:'none', border:'none', color:'var(--muted)', fontSize: "var(--fs-xs)", cursor:'pointer', padding:'2px 6px' }}>
                🗑 清空记录
              </button>
            </div>
          <div style={{ maxHeight: "12.5rem", overflowY: 'auto' }}>
              {/* Error detail modal */}
              {errorDetail && (
                <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: 'rgba(0,0,0,0.6)' }} onClick={() => setErrorDetail(null)}>
                  <div className="rounded-lg p-4 max-w-md max-h-60 overflow-y-auto" style={{ background: 'var(--surface-secondary)', border: '1px solid #444' }} onClick={e => e.stopPropagation()}>
                    <pre style={{ color: 'var(--danger)', fontSize: "var(--fs-sm)", whiteSpace: 'pre-wrap', margin: 0 }}>{errorDetail}</pre>
                  </div>
                </div>
              )}

              {/* Batch actions */}
              {failedCount > 0 && (
                <div className="flex items-center gap-2 px-3 py-1.5 border-b" style={{ borderColor: 'var(--surface-tertiary)' }}>
                  <button onClick={retryAll} style={{ background:'var(--surface-secondary)', color:'var(--accent)', border:'1px solid #444', borderRadius: "0.25rem", padding:'2px 10px', fontSize: "var(--fs-sm)", cursor:'pointer' }}>
                    🔄 一键重试
                  </button>
                </div>
              )}

              {/* Job list */}
              {jobs.slice(0, 15).map(j => (
                <div key={j.job_id} className="flex items-center gap-2 px-3 py-1.5" style={{ borderTop: '1px solid #2A2A2A' }}>
                  {j.status === 'failed' ? (
                    <span style={{ color: 'var(--danger)', fontSize: "var(--fs-md)", flexShrink: 0, cursor: 'pointer' }} title="点击查看详情" onClick={() => setErrorDetail(j.error || '未知错误')}>❗</span>
                  ) : j.status === 'done' ? (
                    <span style={{ color: 'var(--success)', fontSize: "var(--fs-sm)", flexShrink: 0 }}>✅</span>
                  ) : (
                    <span style={{ color: 'var(--accent)', fontSize: "var(--fs-sm)", flexShrink: 0 }}>⏳</span>
                  )}
                  <div className="flex-1 min-w-0">
                    <div style={{ color: 'var(--default-foreground)', fontSize: "var(--fs-sm)", overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{j.source_path}</div>
                    {j.status === 'done' && j.result_summary && (
                      <div style={{ color: 'var(--success)', fontSize: "0.625rem" }}>{j.result_summary}</div>
                    )}
                    {j.status === 'failed' && (
                      <div style={{ color: 'var(--danger)', fontSize: "0.625rem", overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer' }} onClick={() => setErrorDetail(j.error || '未知错误')}>
                        {j.error?.slice(0, 30) || '解析失败'}...
                      </div>
                    )}
                    {j.status === 'processing' && (
                      <div style={{ color: 'var(--accent)', fontSize: "0.625rem" }}>处理中...</div>
                    )}
                  </div>
                  <div className="flex gap-1 flex-shrink-0">
                    {j.status === 'failed' && (
                      <button onClick={() => retryJob(j.job_id)}
                        style={{ width: "1.5rem", height: "1.5rem", borderRadius: '50%', border: '1px solid #444', background: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: "var(--fs-xs)", display: 'flex', alignItems: 'center', justifyContent: 'center' }}>↻</button>
                    )}
                    <button onClick={() => deleteJob(j.job_id)}
                      style={{ width: "1.5rem", height: "1.5rem", borderRadius: '50%', border: '1px solid #444', background: 'none', color: 'var(--muted)', cursor: 'pointer', fontSize: "var(--fs-xs)", display: 'flex', alignItems: 'center', justifyContent: 'center' }}>✕</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
          )}

      </div>

      {/* Close drawer */}
      {queueOpen && (
        <div className="flex items-center justify-center cursor-pointer border-t" style={{ height: "2.625rem", background:'var(--surface)', borderColor:'var(--surface-tertiary)' }}
          onClick={() => setQueueOpen(false)}
          onMouseEnter={e => e.currentTarget.style.background = 'var(--surface-tertiary)'}
          onMouseLeave={e => e.currentTarget.style.background = 'var(--surface)'}
        >
          <span style={{ fontSize: "0.625rem", color:'var(--muted)', display:'flex', alignItems:'center', gap: "0.25rem" }}>▼ 收起</span>
        </div>
      )}
    </aside>
  );
}
