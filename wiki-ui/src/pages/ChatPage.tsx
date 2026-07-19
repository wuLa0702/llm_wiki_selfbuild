import { useState, useRef, useEffect } from 'react';
import { Button, Card, CardContent, Avatar, AvatarFallback, Chip, TextArea, ToggleButtonGroup, ToggleButton, ScrollShadow, EmptyState } from '@heroui/react';

interface Message { role: 'user' | 'assistant'; content: string; skills?: number; id: string; }
interface Session { id: string; title: string; date: string; messages: Message[]; }
function mid() { return Math.random().toString(36).slice(2, 10); }

export default function ChatPage() {
  const [sessions, setSessions] = useState<Session[]>(() => {
    try { return JSON.parse(localStorage.getItem('chat_sessions') || '[]'); } catch { return []; }
  });
  const [activeId, setActiveId] = useState<string>('');
  const [input, setInput] = useState('');
  const [mode, setMode] = useState(new Set(['标准']));
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const inputRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  const active = sessions.find(s => s.id === activeId);

  useEffect(() => { localStorage.setItem('chat_sessions', JSON.stringify(sessions)); }, [sessions]);

  const send = () => {
    const text = input.trim(); if (!text) return;
    let sid = activeId;
    if (!active) {
      const s: Session = { id: mid(), title: text.slice(0, 30), date: new Date().toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }), messages: [] };
      setSessions(prev => [s, ...prev]); sid = s.id; setActiveId(sid);
    }
    const u: Message = { role: 'user', content: text, id: mid() };
    const a: Message = { role: 'assistant', content: '正在生成回复...', skills: 45, id: mid() };
    setSessions(prev => prev.map(s => s.id === sid ? { ...s, title: s.messages.length === 0 ? text.slice(0, 30) : s.title, date: new Date().toLocaleDateString('zh-CN'), messages: [...s.messages, u, a] } : s));
    setInput(''); inputRef.current?.focus();
    setTimeout(() => {
      setSessions(prev => prev.map(s => {
        if (s.id !== sid) return s;
        const m = [...s.messages]; m[m.length - 1] = { ...m[m.length - 1], content: 'AI 回复内容（后续接入 LLM API）', skills: 45 };
        return { ...s, messages: m };
      }));
    }, 1500);
  };

  const copyMsg = (c: string) => navigator.clipboard.writeText(c);
  const regen = () => {
    if (!active) return; const m = [...active.messages]; if (m.length < 2) return;
    m[m.length - 1] = { ...m[m.length - 1], content: '重新生成中...' };
    setSessions(prev => prev.map(s => s.id === activeId ? { ...s, messages: m } : s));
    setTimeout(() => setSessions(prev => prev.map(s => { if (s.id !== activeId) return s; const ms = [...s.messages]; ms[ms.length - 1] = { ...ms[ms.length - 1], content: '已重新生成回复（模拟）' }; return { ...s, messages: ms }; })), 1000);
  };

  const msgN = (s: Session) => s.messages.filter(m => m.role === 'user').length;

  return (
    <div className="flex flex-1 min-h-0 bg-background">
      {/* Left — session sidebar */}
      <div className="flex-shrink-0 flex flex-col border-r border-default-200 bg-surface-secondary transition-all duration-200" style={{ width: sidebarOpen ? 260 : 0, overflow: 'hidden' }}>
        <div className="p-3 flex-shrink-0">
          <Button variant="bordered" startContent={<span>+</span>} className="w-full"
            onPress={() => { setActiveId(''); setInput(''); }}>
            新建对话
          </Button>
        </div>
        <ScrollShadow className="flex-1 px-2 pb-2">
          {sessions.length === 0 ? (
            <div className="text-sm text-default-400 py-8 px-3">暂无对话记录</div>
          ) : sessions.map(s => (
            <div key={s.id}
              className={`px-3 py-2.5 mb-1 rounded-lg cursor-pointer transition-colors ${s.id === activeId ? 'bg-default-100' : 'hover:bg-default-50'}`}
              onClick={() => setActiveId(s.id)}>
              <div className="text-sm truncate">{s.title}</div>
              <div className="text-xs text-default-400 mt-0.5">{s.date} · {msgN(s)} 条消息</div>
            </div>
          ))}
        </ScrollShadow>
      </div>

      {/* Collapse toggle */}
      <div className="flex items-center cursor-pointer flex-shrink-0 w-6 border-r border-default-200 justify-center" onClick={() => setSidebarOpen(!sidebarOpen)}>
        <span className="text-xs text-default-400">{sidebarOpen ? '◀' : '▶'}</span>
      </div>

      {/* Main chat */}
      <div className="flex-1 flex flex-col min-w-0">
        <ScrollShadow className="flex-1" ref={canvasRef}>
          {active ? (
            <div className="px-6 py-6">
              {active.messages.map(msg => (
                <div key={msg.id} className="mb-6">
                  {msg.role === 'user' ? (
                    <div className="flex justify-end">
                      <div className="flex items-start gap-2 max-w-[70%]">
                        <Card color="primary" className="rounded-xl">
                          <CardContent className="px-3.5 py-2.5 text-sm">{msg.content}</CardContent>
                        </Card>
                        <Avatar size="sm" fallback={<AvatarFallback>U</AvatarFallback>} />
                      </div>
                    </div>
                  ) : (
                    <div className="flex justify-start">
                      <div className="max-w-[70%]">
                        {msg.skills && msg.content !== '正在生成回复...' && msg.content !== '重新生成中...' && (
                          <Chip variant="flat" size="sm" className="mb-1">✓ {msg.skills} skill(s) available</Chip>
                        )}
                        <Card variant="bordered" className="rounded-xl">
                          <CardContent className="px-3.5 py-2.5 text-sm whitespace-pre-wrap">{msg.content}</CardContent>
                        </Card>
                        {msg.content !== '正在生成回复...' && msg.content !== '重新生成中...' && (
                          <div className="flex gap-2 mt-2">
                            <Button size="sm" variant="light" onPress={() => copyMsg(msg.content)}>Copy</Button>
                            <Button size="sm" variant="light">Save to Wiki</Button>
                            <Button size="sm" variant="light" onPress={regen}>Regenerate</Button>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-center h-full">
              <EmptyState
                icon={<span className="text-4xl opacity-40">💬</span>}
                title="开始对话"
                description="点击左侧「新建对话」或直接输入消息"
              />
            </div>
          )}
        </ScrollShadow>

        {/* Bottom input — fixed */}
        <Card variant="flat" className="rounded-none border-t border-default-200 flex-shrink-0">
          <CardContent className="p-0">
            <div className="px-4 pt-3">
              <TextArea
                placeholder="输入消息..."
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}
                minRows={1}
                maxRows={6}
                className="w-full"
              />
            </div>
            <div className="flex items-center justify-between px-4 py-2 gap-2">
              <div className="flex gap-1">
                {['添加图片', '网页搜索', 'AnyTXT 搜索', 'Skills'].map(l => (
                  <Button key={l} size="sm" variant="secondary">{l}</Button>
                ))}
              </div>
              <ToggleButtonGroup selectedKeys={mode} onSelectionChange={setMode as any} size="sm" variant="flat">
                <ToggleButton id="快速">快速</ToggleButton>
                <ToggleButton id="标准">标准</ToggleButton>
                <ToggleButton id="深度">深度</ToggleButton>
                <ToggleButton id="本地优先">本地优先</ToggleButton>
              </ToggleButtonGroup>
              <Button color="primary" isDisabled={!input.trim()} onPress={send} endContent={<span>✈</span>}>
                发送消息
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
