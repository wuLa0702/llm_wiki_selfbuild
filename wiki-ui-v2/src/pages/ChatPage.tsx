import { useState, useRef, useEffect } from 'react';
import { MessageSquare, Plus, Send, StopCircle, Copy, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { showToast } from '@/components/shared/Toast';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  id: string;
}

interface Session {
  id: string;
  title: string;
  date: string;
  messages: Message[];
}

function mid() { return Math.random().toString(36).slice(2, 10); }

/** SSE 事件类型 */
interface SseToken { type: 'token'; content: string }
interface SseToolStart { type: 'tool_start'; tool: string; input: Record<string, unknown> }
interface SseToolEnd { type: 'tool_end'; tool: string; output: string }
interface SseDone { type: 'done'; sources: string[] }
interface SseError { type: 'error'; message: string }
type SseEvent = SseToken | SseToolStart | SseToolEnd | SseDone | SseError;

/** 调用后端 Agent 会话版（/session 端点），通过 fetch + ReadableStream 读取 SSE */
async function* agentChatStreamSession(content: string, threadId: string): AsyncGenerator<SseEvent> {
  const res = await fetch('/v1/agent/chat/session', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, thread_id: threadId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(err.error || `HTTP ${res.status}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error('Response body is null');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';  // 保留最后一个不完整的行

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const data: SseEvent = JSON.parse(line.slice(6));
        yield data;
      } catch { /* 忽略解析错误 */ }
    }
  }
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<Session[]>(() => {
    try { return JSON.parse(localStorage.getItem('chat_sessions') || '[]'); } catch { return []; }
  });
  const [activeId, setActiveId] = useState<string>('');
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const active = sessions.find(s => s.id === activeId);

  useEffect(() => {
    localStorage.setItem('chat_sessions', JSON.stringify(sessions));
  }, [sessions]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [sessions, activeId]);

  const newSession = () => {
    const s: Session = {
      id: mid(),
      title: '新对话',
      date: new Date().toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }),
      messages: [],
    };
    setSessions(prev => [s, ...prev]);
    setActiveId(s.id);
    setInput('');
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const streamReply = async (text: string, sid: string) => {
    const userMsg: Message = { role: 'user', content: text, id: mid() };
    const assistantMsg: Message = { role: 'assistant', content: '', id: mid() };

    setSessions(prev => prev.map(s =>
      s.id === sid
        ? { ...s, title: s.messages.length === 0 ? text.slice(0, 30) : s.title, messages: [...s.messages, userMsg, assistantMsg] }
        : s
    ));
    setStreaming(true);

    // 由后端 /session 端点管理历史（持久化 SQLite），
    // 前端只需传本轮 text + session.id 作为 thread_id
    let accumulated = '';

    try {
      for await (const event of agentChatStreamSession(text, sid)) {
        switch (event.type) {
          case 'token':
            accumulated += event.content;
            setSessions(prev => prev.map(s => {
              if (s.id !== sid) return s;
              const msgs = [...s.messages];
              const last = msgs[msgs.length - 1];
              if (last.role === 'assistant') msgs[msgs.length - 1] = { ...last, content: accumulated };
              return { ...s, messages: msgs };
            }));
            break;
          case 'tool_start':
            // 可选：显示"正在搜索..."状态
            break;
          case 'tool_end':
            break;
          case 'done':
            if (event.sources?.length) {
              console.log('Sources:', event.sources);
            }
            break;
          case 'error':
            showToast(`对话出错：${event.message}`, 'error');
            break;
        }
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      showToast(`连接失败：${message}`, 'error');
    }
    setStreaming(false);
  };

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    let sid = activeId;
    if (!active) {
      const s: Session = {
        id: mid(),
        title: text.slice(0, 30),
        date: new Date().toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }),
        messages: [],
      };
      setSessions(prev => [s, ...prev]);
      sid = s.id;
      setActiveId(sid);
    }

    setInput('');
    streamReply(text, sid);
  };

  /* Called by suggestion buttons — creates session + sends immediately */
  const sendSuggestion = (text: string) => {
    if (streaming) return;
    const s: Session = {
      id: mid(),
      title: text.slice(0, 30),
      date: new Date().toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }),
      messages: [],
    };
    setSessions(prev => [s, ...prev]);
    setActiveId(s.id);
    setInput('');
    streamReply(text, s.id);
  };

  const copyMsg = (c: string) => {
    navigator.clipboard.writeText(c);
    showToast('已复制', 'success');
  };

  const msgCount = (s: Session) => s.messages.filter(m => m.role === 'user').length;

  return (
    <div className="flex flex-1 min-h-0">
      {/* Session sidebar */}
      <div
        className="flex-shrink-0 flex flex-col border-r border-border bg-card transition-all duration-200"
        style={{ width: sidebarOpen ? 260 : 0, overflow: 'hidden' }}
      >
        <div className="p-3 border-b border-border">
          <Button
            variant="outline"
            className="w-full justify-start gap-2"
            onClick={newSession}
          >
            <Plus className="h-4 w-4" /> 新建对话
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto p-2">
          {sessions.length === 0 ? (
            <div className="text-xs text-muted-foreground text-center py-8">暂无对话记录</div>
          ) : (
            sessions.map(s => (
              <div
                key={s.id}
                className={`px-3 py-2.5 mb-1 rounded-lg cursor-pointer transition-colors ${
                  s.id === activeId ? 'bg-accent' : 'hover:bg-accent/50'
                }`}
                onClick={() => setActiveId(s.id)}
              >
                <div className="text-sm truncate font-medium">{s.title}</div>
                <div className="text-xs text-muted-foreground mt-0.5">
                  {s.date} · {msgCount(s)} 条消息
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Toggle button */}
      <div
        className="flex items-center cursor-pointer flex-shrink-0 w-6 border-r border-border justify-center hover:bg-accent/50"
        onClick={() => setSidebarOpen(!sidebarOpen)}
      >
        <span className="text-xs text-muted-foreground">{sidebarOpen ? '◀' : '▶'}</span>
      </div>

      {/* Main chat */}
      <div className="flex-1 flex flex-col min-w-0">
        {active ? (
          <>
            {/* Messages */}
            <div className="flex-1 overflow-y-auto">
              <div className="px-4 py-6 max-w-3xl mx-auto space-y-6">
                {active.messages.map(msg => (
                  <div key={msg.id} className="flex gap-3">
                    {msg.role === 'assistant' && (
                      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-medium">
                        AI
                      </div>
                    )}
                    <div className={`flex-1 min-w-0 ${msg.role === 'user' ? 'ml-auto max-w-[75%]' : ''}`}>
                      {msg.role === 'user' ? (
                        <div className="bg-primary text-primary-foreground rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm">
                          {msg.content}
                        </div>
                      ) : (
                        <div>
                          {msg.content ? (
                            <div className="space-y-2">
                              <div className="prose prose-sm dark:prose-invert max-w-none">
                                <div className="text-sm leading-relaxed whitespace-pre-wrap">{msg.content}</div>
                              </div>
                              {!streaming && (
                                <div className="flex gap-2 pt-1">
                                  <button
                                    className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                                    onClick={() => copyMsg(msg.content)}
                                  >
                                    <Copy className="h-3 w-3" /> 复制
                                  </button>
                                  <button className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
                                    <Sparkles className="h-3 w-3" /> 保存到 Wiki
                                  </button>
                                </div>
                              )}
                            </div>
                          ) : (
                            <div className="flex items-center gap-2 text-muted-foreground">
                              <span className="w-2 h-2 rounded-full bg-muted-foreground animate-pulse" />
                              <span className="w-2 h-2 rounded-full bg-muted-foreground animate-pulse" style={{ animationDelay: '0.2s' }} />
                              <span className="w-2 h-2 rounded-full bg-muted-foreground animate-pulse" style={{ animationDelay: '0.4s' }} />
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                    {msg.role === 'user' && (
                      <div className="flex-shrink-0 w-7 h-7 rounded-full bg-secondary text-secondary-foreground flex items-center justify-center text-xs font-medium">
                        U
                      </div>
                    )}
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            </div>

            {/* Input bar */}
            <div className="border-t border-border bg-card p-4">
              <div className="max-w-3xl mx-auto">
                <div className="flex gap-2 items-end">
                  <Textarea
                    ref={inputRef}
                    placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        send();
                      }
                    }}
                    className="min-h-[2.5rem] max-h-32 resize-none"
                    rows={1}
                  />
                  <Button
                    onClick={streaming ? () => setStreaming(false) : send}
                    disabled={!streaming && !input.trim()}
                    className="shrink-0"
                  >
                    {streaming ? (
                      <StopCircle className="h-4 w-4" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </>
        ) : (
          /* Empty state */
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center max-w-md px-6">
              <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mx-auto mb-4">
                <MessageSquare className="h-8 w-8 text-muted-foreground" />
              </div>
              <h2 className="text-lg font-semibold mb-2">开始对话</h2>
              <p className="text-sm text-muted-foreground mb-6">
                向知识库提问，AI 将基于 Wiki 内容回答
              </p>
              <div className="flex flex-wrap gap-2 justify-center">
                {[
                  '什么是异步编程？',
                  'Python 和 JavaScript 的区别',
                  '解释 Docker 容器化部署',
                ].map(suggestion => (
                  <button
                    key={suggestion}
                    className="px-3 py-1.5 text-xs rounded-full border border-border bg-secondary text-secondary-foreground hover:bg-accent"
                    onClick={() => sendSuggestion(suggestion)}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
