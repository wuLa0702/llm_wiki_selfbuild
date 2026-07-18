import { useState } from 'react';

export default function ChatPage() {
  const [messages, setMessages] = useState<{role: string; content: string}[]>([]);
  const [input, setInput] = useState('');

  const send = () => {
    if (!input.trim()) return;
    setMessages(prev => [...prev, { role: 'user', content: input.trim() }]);
    setInput('');
    // TODO: integrate with chat API
  };

  return (
    <div className="flex-1 flex flex-col" style={{ background: 'var(--background)' }}>
      {messages.length === 0 ? (
        <div className="flex-1 flex items-center justify-center" style={{ color: 'var(--muted)' }}>
          <div className="text-center">
            <div style={{ fontSize: "2rem", marginBottom: "0.5rem" }}>💬</div>
            <p style={{ fontSize: "var(--fs-md)" }}>开始对话</p>
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {messages.map((m, i) => (
            <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className="max-w-[70%] rounded-lg px-3 py-2 text-sm"
                style={{
                  background: m.role === 'user' ? 'var(--accent)' : 'var(--surface-secondary)',
                  color: 'var(--foreground)',
                }}
              >
                {m.content}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="p-3 border-t" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
        <div className="flex gap-2">
          <input
            className="flex-1 px-3 py-2 rounded text-sm outline-none"
            style={{ background: 'var(--surface-secondary)', color: 'var(--default-foreground)', border: '1px solid #333' }}
            placeholder="输入消息..."
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send()}
          />
          <button
            className="px-4 py-2 rounded text-sm"
            style={{ background: 'var(--accent)', color: 'var(--accent-foreground)', border: 'none', cursor: 'pointer' }}
            onClick={send}
          >
            发送
          </button>
        </div>
      </div>
    </div>
  );
}
