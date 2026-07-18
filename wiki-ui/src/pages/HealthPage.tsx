import { useEffect, useState } from 'react';

export default function HealthPage() {
  const [status, setStatus] = useState<'loading' | 'ok' | 'error'>('loading');
  const [detail, setDetail] = useState('');

  useEffect(() => {
    fetch('/health')
      .then(r => r.json())
      .then(d => { setStatus(d.status === 'ok' ? 'ok' : 'error'); setDetail(JSON.stringify(d, null, 2)); })
      .catch(e => { setStatus('error'); setDetail(e.message); });
  }, []);

  return (
    <div className="flex-1 p-6 overflow-y-auto">
      <h1 className="text-xl font-bold mb-1">健康检查</h1>
      <p className="text-xs text-gray-400 mb-4">系统运行状态</p>
      <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm ${
        status === 'loading' ? 'bg-gray-100 text-gray-500' :
        status === 'ok' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
      }`}>
        <span className={`w-2 h-2 rounded-full ${status === 'loading' ? 'bg-gray-400 animate-pulse' : status === 'ok' ? 'bg-green-500' : 'bg-red-500'}`} />
        {status === 'loading' ? '检查中...' : status === 'ok' ? '服务正常' : '服务异常'}
      </div>
      {detail && (
        <pre className="mt-4 text-xs bg-gray-50 dark:bg-neutral-900 p-4 rounded-lg overflow-x-auto">{detail}</pre>
      )}
    </div>
  );
}
