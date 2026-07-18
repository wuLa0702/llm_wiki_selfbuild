import { useState } from 'react';

export default function QueryPage() {
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState<string[]>([]);
  const [confidence, setConfidence] = useState('');
  const [loading, setLoading] = useState(false);

  const handleQuery = async () => {
    if (!question.trim()) return;
    setLoading(true);
    setAnswer('');
    setSources([]);
    try {
      const r = await fetch('/v1/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: question.trim() }),
      });
      const d = await r.json();
      setAnswer(d.answer || '（无回答）');
      setSources(d.sources || []);
      setConfidence(d.confidence || '');
    } catch (e: any) {
      setAnswer(`查询失败: ${e.message}`);
    }
    setLoading(false);
  };

  const confidenceColor: Record<string, string> = {
    high: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
    medium: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
    low: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  };

  return (
    <div className="flex-1 p-6 overflow-y-auto">
      <h1 className="text-xl font-bold mb-1">问答</h1>
      <p className="text-xs text-gray-400 mb-4">向 Wiki 知识库提问</p>

      <div className="flex gap-2 mb-4">
        <input
          className="flex-1 px-3 py-2 text-sm border border-gray-200 dark:border-neutral-700 rounded-lg bg-white dark:bg-neutral-800 outline-none focus:border-blue-400"
          placeholder="输入你的问题..."
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleQuery()}
        />
        <button
          className="px-4 py-2 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 disabled:opacity-50"
          onClick={handleQuery}
          disabled={loading || !question.trim()}
        >
          {loading ? '查询中...' : '提问'}
        </button>
      </div>

      {answer && (
        <div className="bg-gray-50 dark:bg-neutral-900 border border-gray-200 dark:border-neutral-700 rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <h2 className="text-sm font-semibold">回答</h2>
            {confidence && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${confidenceColor[confidence] || ''}`}>
                {confidence}
              </span>
            )}
          </div>
          <div className="text-sm leading-relaxed whitespace-pre-wrap">{answer}</div>
          {sources.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-200 dark:border-neutral-700">
              <h3 className="text-[10px] font-medium text-gray-400 mb-1">来源</h3>
              <div className="flex flex-wrap gap-1">
                {sources.map(s => (
                  <span key={s} className="text-[10px] px-1.5 py-0.5 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 rounded">{s}</span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
