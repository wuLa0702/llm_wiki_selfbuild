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

/* ─── Simulated AI responses (no backend calls) ─── */
const MOCK_RESPONSES: Record<string, string> = {
  async: '异步编程是一种并发编程范式，允许程序在等待 I/O 操作时继续执行其他任务，而不是阻塞线程。在 Python 中通过 `async/await` 语法实现，JavaScript 通过 `Promise` 和 `async/await` 实现。核心思想是将耗时操作委托给事件循环，在等待期间让出 CPU 给其他任务。',
  python: 'Python 是一种动态类型、解释型的高级编程语言，以简洁易读的语法著称。它支持多种编程范式（面向对象、函数式、过程式）。**与 JavaScript 的主要区别：**\n\n1. **类型系统：** Python 是动态强类型，JS 是动态弱类型\n2. **运行环境：** Python 主要在服务端，JS 在浏览器和 Node.js\n3. **并发模型：** Python 多线程受 GIL 限制，JS 单线程事件循环\n4. **语法风格：** Python 用缩进，JS 用花括号',
  docker: 'Docker 是一种容器化平台，将应用及其依赖打包到轻量级容器中，实现"一次构建，到处运行"。\n\n**核心概念：**\n- **镜像（Image）：** 只读模板，包含应用运行所需的一切\n- **容器（Container）：** 镜像的运行实例，独立隔离\n- **Dockerfile：** 描述镜像构建步骤的脚本\n- **docker-compose：** 编排多容器应用\n\n容器相比虚拟机的优势：启动快（秒级）、资源占用小、密度高。',
  default: '这是一个模拟回复。当前对话系统为前端模拟模式，未对接真实 AI 模型。\n\n您可以继续输入问题测试交互流程，包括：\n- 流式打字机动画效果\n- 消息气泡左右布局\n- 会话管理功能\n\n实际部署时，系统将通过后端 LLM 接口返回真实回答。',
};

function mockReply(question: string): string {
  const q = question.toLowerCase();
  if (q.includes('异步') || q.includes('async')) return MOCK_RESPONSES.async;
  if (q.includes('python') || q.includes('js') || q.includes('javascript')) return MOCK_RESPONSES.python;
  if (q.includes('docker') || q.includes('容器')) return MOCK_RESPONSES.docker;
  return MOCK_RESPONSES.default;
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
    // Auto-focus input after next render
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

    const answer = mockReply(text);
    const delay = 300 + Math.random() * 400;
    await new Promise(r => setTimeout(r, delay));

    let idx = 0;
    const interval = setInterval(() => {
      idx += 2;
      const chunk = answer.slice(0, idx);
      setSessions(prev => prev.map(s => {
        if (s.id !== sid) return s;
        const msgs = [...s.messages];
        const last = msgs[msgs.length - 1];
        if (last.role === 'assistant') msgs[msgs.length - 1] = { ...last, content: chunk };
        return { ...s, messages: msgs };
      }));
      if (idx >= answer.length) { clearInterval(interval); setStreaming(false); }
    }, 25);
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
