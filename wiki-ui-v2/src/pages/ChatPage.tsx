/**
 * ChatPage — Agent 对话页（对接后端持久化）
 *
 * 功能：
 *   - 会话列表来自 GET /v1/agent/threads（后端 SQLite 持久化）
 *   - 新建：前端生成 UUID，首条消息发出时落库
 *   - 删除/重命名：侧栏菜单操作，调 DELETE / PATCH
 *   - 消息历史：懒加载，点进会话时 GET detail（含 messages）
 *   - 对话：POST /v1/agent/chat/session SSE 流式
 *   - 工具调用：tool_start / tool_end 事件实时展示
 *   - 中断：AbortController 停止生成
 *
 * 架构说明：
 *   - 所有数据源以**后端为准**，前端只维护：
 *       · threads 列表（元数据）
 *       · messagesByThread 本地缓存（Map<thread_id, messages>）
 *       · toolCallsByAssistantMsg 工具调用展示
 *   - 不再用 localStorage 存 sessions（旧数据由迁移逻辑处理）
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { MessageSquare, Send, StopCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { showToast } from '@/components/shared/Toast';
import ChatSidebar from '@/components/chat/ChatSidebar';
import ChatMessage from '@/components/chat/ChatMessage';
import {
  listThreads, getThread, renameThread, deleteThread, openSessionStream,
} from '@/api/agent';
import type {
  ThreadMeta, ChatMessage as ApiChatMessage, ToolCall as ApiToolCall,
} from '@/api/agent';
import type { ToolCallInfo } from '@/components/chat/ToolCallBadge';

function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

/** 将后端返回的消息归一化为前端展示用（过滤 tool 角色消息） */
function normalizeMessages(raw: ApiChatMessage[]): { visible: ApiChatMessage[]; toolsByAssistantIdx: Map<number, ToolCallInfo[]> } {
  const visible: ApiChatMessage[] = [];
  const toolsByAssistantIdx = new Map<number, ToolCallInfo[]>();
  const toolOutputsById = new Map<string, string>();

  // 先收集所有 tool 输出（role=tool）
  for (const m of raw) {
    if (m.role === 'tool' && m.tool_call_id) {
      toolOutputsById.set(m.tool_call_id, m.content);
    }
  }

  for (const m of raw) {
    if (m.role === 'tool') continue;
    if (m.role === 'system') continue;
    if (m.role === 'assistant' && m.tool_calls && m.tool_calls.length) {
      // assistant 发起工具调用 — 记录工具调用信息，并把消息本身加入可见
      const idx = visible.length;
      const tools: ToolCallInfo[] = m.tool_calls.map((tc: ApiToolCall) => {
        let input: Record<string, unknown> = {};
        try { input = JSON.parse(tc.function.arguments || '{}'); } catch { /* ignore */ }
        const out = toolOutputsById.get(tc.id);
        return {
          id: tc.id,
          name: tc.function.name,
          input,
          output: out,
          status: out ? 'done' : 'running',
        };
      });
      toolsByAssistantIdx.set(idx, tools);
      // assistant 消息有 tool_calls 时 content 可能为空，仍保留展示工具徽标
      visible.push({ role: 'assistant', content: m.content || '' });
    } else {
      visible.push({ role: m.role, content: m.content || '' });
    }
  }
  return { visible, toolsByAssistantIdx };
}

export default function ChatPage() {
  // ── 状态 ────────────────────────────────────────────────────────────────
  const [threads, setThreads] = useState<ThreadMeta[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [activeId, setActiveId] = useState<string>('');
  const [messagesByThread, setMessagesByThread] = useState<Record<string, ApiChatMessage[]>>({});
  const [toolMapByThread, setToolMapByThread] = useState<Record<string, Map<number, ToolCallInfo[]>>>({});
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [sending, setSending] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const listRefreshTimer = useRef<number | null>(null);

  // ── 数据加载 ────────────────────────────────────────────────────────────
  const refreshThreads = useCallback(async (silent = false) => {
    if (!silent) setLoadingList(true);
    try {
      const list = await listThreads(50, 0);
      setThreads(list);
      return list;
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      if (!silent) showToast(`加载会话列表失败：${message}`, 'error');
      return [];
    } finally {
      setLoadingList(false);
    }
  }, []);

  const loadThreadMessages = useCallback(async (threadId: string) => {
    // 已有缓存直接用
    if (messagesByThread[threadId]) return;
    try {
      const detail = await getThread(threadId);
      const { visible, toolsByAssistantIdx } = normalizeMessages(detail.messages);
      setMessagesByThread(prev => ({ ...prev, [threadId]: visible }));
      setToolMapByThread(prev => ({ ...prev, [threadId]: toolsByAssistantIdx }));
      // 同步更新列表里的标题/计数（防止 list 缓存过期）
      setThreads(prev => prev.map(t => t.thread_id === threadId
        ? { ...t, title: detail.title, message_count: visible.filter(m => m.role === 'user').length }
        : t));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      showToast(`加载会话失败：${message}`, 'error');
    }
  }, [messagesByThread]);

  // 首次加载
  useEffect(() => {
    refreshThreads();
    return () => {
      if (listRefreshTimer.current) window.clearTimeout(listRefreshTimer.current);
      abortRef.current?.abort();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 选中会话时懒加载
  useEffect(() => {
    if (activeId && !messagesByThread[activeId]) {
      loadThreadMessages(activeId);
    }
  }, [activeId, loadThreadMessages, messagesByThread]);

  // 自动滚动到底
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeId, messagesByThread]);

  // ── 操作 ────────────────────────────────────────────────────────────────
  const handleNew = () => {
    setActiveId('');
    setInput('');
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  const handleSelect = (id: string) => {
    if (streaming) return;
    setActiveId(id);
  };

  const handleRename = async (id: string, newTitle: string) => {
    try {
      const res = await renameThread(id, newTitle);
      setThreads(prev => prev.map(t => t.thread_id === id ? { ...t, title: res.title } : t));
      showToast('已重命名', 'success');
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      showToast(`重命名失败：${message}`, 'error');
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteThread(id);
      setThreads(prev => prev.filter(t => t.thread_id !== id));
      setMessagesByThread(prev => {
        const { [id]: _, ...rest } = prev; return rest;
      });
      setToolMapByThread(prev => {
        const { [id]: _, ...rest } = prev; return rest;
      });
      if (activeId === id) setActiveId('');
      showToast('已删除', 'success');
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      showToast(`删除失败：${message}`, 'error');
    }
  };

  // ── 发送 / 流式 ────────────────────────────────────────────────────────
  const streamReply = async (text: string, threadId: string) => {
    const userMsg: ApiChatMessage = { role: 'user', content: text };
    const assistantMsg: ApiChatMessage = { role: 'assistant', content: '' };

    // 本地立即插入 user + 空 assistant 占位
    setMessagesByThread(prev => {
      const existing = prev[threadId] || [];
      return { ...prev, [threadId]: [...existing, userMsg, assistantMsg] };
    });
    setToolMapByThread(prev => {
      const map = new Map(prev[threadId] || []);
      const assistantIdx = (prev[threadId] ? messagesByThread[threadId].length : 0) + 1;
      map.set(assistantIdx, []);
      return { ...prev, [threadId]: map };
    });

    setStreaming(true);
    setSending(true);
    const ac = new AbortController();
    abortRef.current = ac;

    let accumulated = '';
    let currentTool: ToolCallInfo | null = null;

    try {
      for await (const event of openSessionStream({
        content: text, threadId, signal: ac.signal,
      })) {
        switch (event.type) {
          case 'token':
            accumulated += event.content;
            setMessagesByThread(prev => {
              const msgs = [...(prev[threadId] || [])];
              const lastIdx = msgs.length - 1;
              if (lastIdx >= 0 && msgs[lastIdx].role === 'assistant') {
                msgs[lastIdx] = { ...msgs[lastIdx], content: accumulated };
              }
              return { ...prev, [threadId]: msgs };
            });
            break;

          case 'tool_start': {
            const tool: ToolCallInfo = {
              id: event.tool + '-' + Date.now(),
              name: event.tool,
              input: event.input,
              status: 'running',
            };
            currentTool = tool;
            setToolMapByThread(prev => {
              const map = new Map(prev[threadId] || []);
              // 找到最后一个 assistant 的 idx
              const msgs = messagesByThread[threadId] || [];
              const assistantIdx = msgs.length - 1;
              const existing = map.get(assistantIdx) || [];
              map.set(assistantIdx, [...existing, tool]);
              return { ...prev, [threadId]: map };
            });
            break;
          }

          case 'tool_end':
            if (currentTool && currentTool.name === event.tool) {
              currentTool.status = 'done';
              currentTool.output = event.output;
              // 触发重渲染（替换 tool 对象）
              setToolMapByThread(prev => {
                const map = new Map(prev[threadId] || []);
                const msgs = messagesByThread[threadId] || [];
                const assistantIdx = msgs.length - 1;
                const arr = (map.get(assistantIdx) || []).map(t =>
                  t.id === currentTool!.id ? { ...currentTool! } : t);
                map.set(assistantIdx, arr);
                return { ...prev, [threadId]: map };
              });
              currentTool = null;
            }
            break;

          case 'tool_approval_needed':
            // 未来人工审批接入点，当前只打日志
            console.log('[agent] approval needed:', event);
            break;

          case 'error':
            showToast(`对话出错：${event.message}`, 'error');
            break;

          case 'done':
            // 刷新会话列表（标题/更新时间/消息数由后端生成）
            listRefreshTimer.current = window.setTimeout(() => refreshThreads(true), 800);
            break;
        }
      }
    } catch (err: unknown) {
      if ((err as Error)?.name === 'AbortError') {
        showToast('已停止生成', 'info');
      } else {
        const message = err instanceof Error ? err.message : String(err);
        showToast(`连接失败：${message}`, 'error');
      }
    } finally {
      setStreaming(false);
      setSending(false);
      abortRef.current = null;
    }
  };

  const send = async () => {
    const text = input.trim();
    if (!text || streaming) return;

    let sid = activeId;
    if (!sid) {
      sid = newId();
      setActiveId(sid);
      setMessagesByThread(prev => ({ ...prev, [sid]: [] }));
      setToolMapByThread(prev => ({ ...prev, [sid]: new Map() }));
    }
    setInput('');
    await streamReply(text, sid);
  };

  const handleStop = () => {
    abortRef.current?.abort();
  };

  const active = threads.find(t => t.thread_id === activeId);
  const activeMessages = messagesByThread[activeId] || (activeId ? undefined : []) || [];
  const activeTools = toolMapByThread[activeId] || new Map();
  const hasActive = activeMessages.length > 0;

  const suggestions = [
    '什么是异步编程？',
    'Python 和 JavaScript 的区别',
    '解释 Docker 容器化部署',
  ];

  return (
    <div className="flex flex-1 min-h-0">
      {/* Sidebar */}
      <div
        className="flex-shrink-0 transition-all duration-200 overflow-hidden"
        style={{ width: sidebarOpen ? 260 : 0 }}
      >
        <ChatSidebar
          threads={threads}
          activeId={activeId}
          loading={loadingList}
          onSelect={handleSelect}
          onNew={handleNew}
          onRename={handleRename}
          onDelete={handleDelete}
        />
      </div>

      {/* Toggle button */}
      <div
        className="flex items-center cursor-pointer flex-shrink-0 w-6 border-r border-border justify-center hover:bg-accent/50"
        onClick={() => setSidebarOpen(!sidebarOpen)}
        title={sidebarOpen ? '收起侧栏' : '展开侧栏'}
      >
        <span className="text-xs text-muted-foreground">{sidebarOpen ? '◀' : '▶'}</span>
      </div>

      {/* Main chat */}
      <div className="flex-1 flex flex-col min-w-0">
        {hasActive ? (
          <>
            {/* 顶部标题栏 */}
            <div className="border-b border-border px-4 py-2.5 flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium truncate">
                {active?.title || '新对话'}
              </span>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto">
              <div className="px-4 py-6 max-w-3xl mx-auto space-y-6">
                {activeMessages.map((msg, idx) => (
                  <ChatMessage
                    key={`${activeId}-${idx}`}
                    message={msg}
                    toolCalls={msg.role === 'assistant' ? activeTools.get(idx) : undefined}
                    isStreaming={streaming && idx === activeMessages.length - 1 && msg.role === 'assistant'}
                    onCopy={() => showToast('已复制', 'success')}
                  />
                ))}
                <div ref={messagesEndRef} />
              </div>
            </div>

            {/* Input */}
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
                    disabled={sending && !streaming}
                  />
                  <Button
                    onClick={streaming ? handleStop : send}
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
              <div className="flex flex-wrap gap-2 justify-center mb-6">
                {suggestions.map(s => (
                  <button
                    key={s}
                    disabled={streaming}
                    className="px-3 py-1.5 text-xs rounded-full border border-border bg-secondary text-secondary-foreground hover:bg-accent disabled:opacity-50"
                    onClick={() => setInput(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
              <div className="max-w-xl mx-auto">
                <div className="flex gap-2 items-end">
                  <Textarea
                    ref={inputRef}
                    placeholder="输入消息开始新对话..."
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
                    onClick={send}
                    disabled={!input.trim() || streaming}
                  >
                    <Send className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
