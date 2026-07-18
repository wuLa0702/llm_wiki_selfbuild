import { useEffect, useState } from 'react';
import { showToast } from './Toast';

interface QueueJob {
  job_id: string;
  source_path: string;
  status: string;
  error?: string;
  result_summary?: string;
}

const STATUS_ICON: Record<string, string> = {
  pending: '⏳', processing: '🔄', done: '✅', failed: '❌', cancelled: '🚫',
};

export default function TaskQueue() {
  const [jobs, setJobs] = useState<QueueJob[]>([]);
  const [stats, setStats] = useState({ pending: 0, processing: 0, done: 0, failed: 0 });

  useEffect(() => {
    const fetchStatus = () => {
      Promise.all([
        fetch('/v1/ingest/queue/recent?limit=20').then(r => r.json()),
        fetch('/v1/ingest/queue/status').then(r => r.json()),
      ]).then(([recent, status]) => {
        setJobs(recent.jobs || []);
        setStats(status);
      }).catch(() => {});
    };
    fetchStatus();
    const id = setInterval(fetchStatus, 5000);
    return () => clearInterval(id);
  }, []);

  const deleteJob = (jobId: string) => {
    if (!confirm('确定删除此任务记录？')) return;
    fetch(`/v1/ingest/queue/${jobId}`, { method: 'DELETE' })
      .then(() => {
        setJobs(prev => prev.filter(j => j.job_id !== jobId));
        showToast('已删除', 'success');
      })
      .catch(() => showToast('删除失败', 'error'));
  };

  const retryJob = (jobId: string) => {
    fetch(`/v1/ingest/queue/retry/${jobId}`, { method: 'POST' })
      .then(() => showToast('已重新加入队列', 'success'))
      .catch(() => showToast('重试失败', 'error'));
  };

  const retryAll = async () => {
    const failed = jobs.filter(j => j.status === 'failed');
    if (!failed.length) { showToast('没有失败任务', 'info'); return; }
    let count = 0;
    for (const j of failed) {
      try {
        await fetch(`/v1/ingest/queue/retry/${j.job_id}`, { method: 'POST' });
        count++;
      } catch {}
    }
    showToast(`已重试 ${count}/${failed.length} 个`, 'success');
  };

  return (
    <div className="border-t border-gray-200 dark:border-neutral-700">
      <div className="flex gap-2 px-3 py-1.5 border-b border-gray-100 dark:border-neutral-800">
        {[
          { label: `排队 ${stats.pending}`, cls: 'bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400' },
          { label: `处理中 ${stats.processing}`, cls: 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400' },
          { label: `成功 ${stats.done}`, cls: 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400' },
          { label: `失败 ${stats.failed}`, cls: 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400' },
        ].map(s => (
          <span key={s.label} className={`text-[10px] px-1.5 py-0.5 rounded-full ${s.cls}`}>{s.label}</span>
        ))}
      </div>

      <div className="max-h-40 overflow-y-auto">
        {jobs.length === 0 ? (
          <div className="text-[10px] text-gray-400 text-center py-2">暂无任务</div>
        ) : (
          <>
            {stats.failed > 0 && (
              <div className="flex gap-1 px-3 py-1 border-b border-gray-100 dark:border-neutral-800">
                <button className="text-[9px] px-1.5 py-0.5 rounded bg-red-50 dark:bg-red-900/20 text-red-600 hover:bg-red-100" onClick={retryAll}>
                  🔄 重试全部失败
                </button>
              </div>
            )}
            {jobs.map(j => (
              <div key={j.job_id} className="flex items-center gap-1 px-3 py-1 text-[11px] hover:bg-gray-50 dark:hover:bg-neutral-800 group">
                <span>{STATUS_ICON[j.status] || '❓'}</span>
                <span className="flex-1 truncate text-gray-600 dark:text-gray-400">{j.source_path || j.job_id}</span>
                {j.status === 'failed' && (
                  <span className="text-red-500 truncate max-w-[80px]" title={j.error}>{j.error?.slice(0, 15) || '失败'}</span>
                )}
                {j.status === 'done' && j.result_summary && (
                  <span className="text-green-600 dark:text-green-400 text-[9px]">{j.result_summary}</span>
                )}
                <span className="hidden group-hover:flex gap-0.5">
                  {j.status === 'failed' && (
                    <button className="text-[9px] px-1 py-0.5 rounded text-gray-400 hover:text-blue-500" title="重试" onClick={() => retryJob(j.job_id)}>↻</button>
                  )}
                  <button className="text-[9px] px-1 py-0.5 rounded text-gray-400 hover:text-red-500" title="删除" onClick={() => deleteJob(j.job_id)}>✕</button>
                </span>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
