import { useEffect, useState } from 'react';
import { showToast } from '../components/Toast';

interface LintResult {
  broken_links?: { source: string; target: string }[];
  orphan_pages?: string[];
  shallow_pages?: { path: string; word_count: number }[];
  summary?: string;
}

export default function LintPage() {
  const [result, setResult] = useState<LintResult | null>(null);
  const [loading, setLoading] = useState(false);

  const runLint = async (semantic = false) => {
    setLoading(true);
    try {
      const r = await fetch(`/v1/lint?semantic=${semantic}`);
      const d = await r.json();
      setResult(d);
      showToast('检查完成', 'success');
    } catch { showToast('检查失败', 'error'); }
    setLoading(false);
  };

  useEffect(() => { runLint(false); }, []);

  return (
    <div className="flex-1 p-6 overflow-y-auto">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold mb-1">Lint 检查</h1>
          <p className="text-xs text-gray-400">Wiki 知识库质量检查</p>
        </div>
        <div className="flex gap-2">
          <button className="text-xs px-3 py-1.5 rounded bg-gray-200 dark:bg-neutral-700 hover:bg-gray-300" onClick={() => runLint(false)} disabled={loading}>
            {loading ? '检查中...' : '🔍 检查'}
          </button>
          <button className="text-xs px-3 py-1.5 rounded bg-blue-500 text-white hover:bg-blue-600" onClick={() => runLint(true)} disabled={loading}>
            {loading ? '检查中...' : '🧠 语义检查'}
          </button>
        </div>
      </div>

      {result && (
        <div className="space-y-4">
          {result.summary && (
            <div className="bg-gray-50 dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 rounded-lg p-4">
              <p className="text-sm">{result.summary}</p>
            </div>
          )}

          {result.broken_links && result.broken_links.length > 0 && (
            <section className="bg-gray-50 dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 rounded-lg p-4">
              <h2 className="text-sm font-semibold mb-2 text-red-600 dark:text-red-400">断链 ({result.broken_links.length})</h2>
              <div className="space-y-1">
                {result.broken_links.map((bl, i) => (
                  <div key={i} className="text-xs text-gray-600 dark:text-gray-400">
                    <span className="text-red-500">{bl.source}</span> → <span className="text-gray-400">{bl.target}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {result.orphan_pages && result.orphan_pages.length > 0 && (
            <section className="bg-gray-50 dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 rounded-lg p-4">
              <h2 className="text-sm font-semibold mb-2 text-amber-600 dark:text-amber-400">孤立页面 ({result.orphan_pages.length})</h2>
              <div className="flex flex-wrap gap-1">
                {result.orphan_pages.map(p => (
                  <span key={p} className="text-[10px] px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400">{p}</span>
                ))}
              </div>
            </section>
          )}

          {(!result.broken_links?.length && !result.orphan_pages?.length) && (
            <div className="text-center py-8 text-gray-400 text-sm">✅ 未发现问题</div>
          )}
        </div>
      )}
    </div>
  );
}
