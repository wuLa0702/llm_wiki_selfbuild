/**
 * ChatPage — Agent 对话页（前后端联调版）
 *
 * 功能：
 *   - 会话列表来自 GET /v1/agent/threads（后端 SQLite 持久化）
 *   - 新建：前端生成 UUID，首条消息发出时落库
 *   - 删除/重命名/清空：调后端 API
 *   - 消息历史：懒加载，点进会话时 GET detail
 *   - 对话：POST /v1/agent/chat/session SSE 流式
 *   - 工具调用：tool_start / tool_end 事件实时展示
 *   - 引用卡片：done 事件中的 cited_pages 渲染
 *   - 重新生成：POST /v1/agent/threads/{id}/regenerate SSE
 *   - 反馈：POST /v1/agent/threads/{id}/feedback
 *   - 模型列表：GET /v1/agent/models
 *   - 中断：AbortController 停止生成
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MessageSquare, Send, Trash2, Loader2, ChevronDown,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { showToast } from '@/components/shared/Toast';
import { showConfirm } from '@/components/ui/confirm-dialog';
import ChatSidebar from '@/components/chat/ChatSidebar';
import ChatMessage from '@/components/chat/ChatMessage';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  listThreads, getThread, renameThread, deleteThread, clearThread,
  openSessionStream, regenerateStream, submitFeedback, listModels,
} from '@/api/agent';
import type {
  ChatMessage as ApiChatMessage, ThreadMeta, ModelInfo, CitedPage,
  ToolCall as ApiToolCall,
} from '@/api/agent';
import type { CitationInfo } from '@/components/chat/ChatMessage';
import type { ToolCallInfo } from '@/components/chat/ToolCallBadge';

const SUGGESTIONS = [
  '什么是 LangGraph 状态管理？',
  '解释异步编程的核心概念',
  '向量数据库怎么选？',
  'RAG 的检索策略有哪些？',
];

function newId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID();
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

/** 将后端返回的消息归一化为前端展示用（过滤 tool/system 角色消息） */
function normalizeMessages(raw: ApiChatMessage[]): {
  visible: ApiChatMessage[];
  toolsByAssistantIdx: Map<number, ToolCallInfo[]>;
} {
  const visible: ApiChatMessage[] = [];
  const toolsByAssistantIdx = new Map<number, ToolCallInfo[]>();
  const toolOutputsById = new Map<string, string>();

  for (const m of raw) {
    if (m.role === 'tool' && m.tool_call_id) {
      toolOutputsById.set(m.tool_call_id, m.content);
    }
  }

  for (const m of raw) {
    if (m.role === 'tool' || m.role === 'system') continue;
    if (m.role === 'assistant' && m.tool_calls && m.tool_calls.length) {
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
      visible.push({ role: 'assistant', content: m.content || '' });
    } else {
      visible.push({ role: m.role, content: m.content || '' });
    }
  }
  return { visible, toolsByAssistantIdx };
}

// ── 组件 ─────────────────────────────────────────────────────────────────

export default function ChatPage() {
  const navigate = useNavigate();
  const [threads, setThreads] = useState<ThreadMeta[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [activeId, setActiveId] = useState<string>('');
  const [messagesByThread, setMessagesByThread] = useState<Record<string, ApiChatMessage[]>>({});
  const [toolMapByThread, setToolMapByThread] = useState<Record<string, Map<number, ToolCallInfo[]>>>({});
  const [citationsByThread, setCitationsByThread] = useState<Record<string, Map<number, CitationInfo[]>>>({});
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [currentModelId, setCurrentModelId] = useState<string>('');
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [pageVisible, setPageVisible] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const listRefreshTimer = useRef<number | null>(null);

  // 页面进入动画 + 首次加载数据
  useEffect(() => {
    const t = setTimeout(() => setPageVisible(true), 30);
    refreshThreads();
    loadModels();
    return () => {
      clearTimeout(t);
      if (listRefreshTimer.current) window.clearTimeout(listRefreshTimer.current);
      abortRef.current?.abort();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 选中会话时懒加载消息
  useEffect(() => {
    if (activeId && !messagesByThread[activeId]) {
      loadThreadMessages(activeId);
    }
  }, [activeId]); // eslint-disable-line react-hooks/exhaustive-deps

  // 自动滚动
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [activeId, messagesByThread]);

  // ── 数据加载 ──────────────────────────────────────────────────────────
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
    try {
      const detail = await getThread(threadId);
      const { visible, toolsByAssistantIdx } = normalizeMessages(detail.messages);
      setMessagesByThread(prev => ({ ...prev, [threadId]: visible }));
      setToolMapByThread(prev => ({ ...prev, [threadId]: toolsByAssistantIdx }));
      // 同步更新列表元数据
      setThreads(prev => prev.map(t => t.thread_id === threadId
        ? { ...t, title: detail.title, message_count: visible.filter(m => m.role === 'user').length }
        : t));
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      showToast(`加载会话失败：${message}`, 'error');
    }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      const data = await listModels();
      setModels(data.models);
      setCurrentModelId(data.current.id);
    } catch {
      // 模型列表加载失败不阻塞主功能
    }
  }, []);

  // ── 操作 ──────────────────────────────────────────────────────────────
  const handleNew = useCallback(() => {
    setActiveId('');
    setInput('');
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  const handleSelect = useCallback((id: string) => {
    if (streaming) return;
    setActiveId(id);
  }, [streaming]);

  const handleRename = useCallback(async (id: string, newTitle: string) => {
    try {
      const res = await renameThread(id, newTitle);
      setThreads(prev => prev.map(t => t.thread_id === id ? { ...t, title: res.title } : t));
      showToast('已重命名', 'success');
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      showToast(`重命名失败：${message}`, 'error');
    }
  }, []);

  const handleDelete = useCallback(async (id: string) => {
    try {
      await deleteThread(id);
      setThreads(prev => prev.filter(t => t.thread_id !== id));
      setMessagesByThread(prev => { const { [id]: _, ...rest } = prev; return rest; });
      setToolMapByThread(prev => { const { [id]: _, ...rest } = prev; return rest; });
      setCitationsByThread(prev => { const { [id]: _, ...rest } = prev; return rest; });
      if (activeId === id) setActiveId('');
      showToast('已删除', 'success');
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      showToast(`删除失败：${message}`, 'error');
    }
  }, [activeId]);

  const handleClearChat = useCallback(async () => {
    if (!activeId) return;
    try {
      await clearThread(activeId);
      setMessagesByThread(prev => ({ ...prev, [activeId]: [] }));
      setToolMapByThread(prev => ({ ...prev, [activeId]: new Map() }));
      setCitationsByThread(prev => ({ ...prev, [activeId]: new Map() }));
      showToast('对话已清空', 'success');
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      showToast(`清空失败：${message}`, 'error');
    }
  }, [activeId]);

  // 导航到 wiki 页面
  const handleNavigate = useCallback((wikiPath: string) => {
    navigate(`/wiki?path=${encodeURIComponent(wikiPath)}`);
  }, [navigate]);

  const handleCitationClick = useCallback((c: CitationInfo) => {
    if (c.path) {
      const cleanPath = c.path.replace(/^wiki\//, '');
      navigate(`/wiki?path=${encodeURIComponent(cleanPath)}`);
    }
  }, [navigate]);

  // ── SSE 流式发送 / 重新生成 ───────────────────────────────────────────
  const streamReply = useCallback(async (
    text: string,
    threadId: string,
    isRegenerate = false,
    approval?: { approved: boolean },
  ) => {
    const userMsg: ApiChatMessage = { role: 'user', content: text };
    const assistantMsg: ApiChatMessage = { role: 'assistant', content: '' };

    // 只有非 approval 恢复时才插入新的 user + assistant 消息
    if (!approval) {
      if (!isRegenerate) {
        setMessagesByThread(prev => {
          const existing = prev[threadId] || [];
          return { ...prev, [threadId]: [...existing, userMsg, assistantMsg] };
        });
      } else {
        setMessagesByThread(prev => {
          const msgs = [...(prev[threadId] || [])];
          while (msgs.length > 0 && msgs[msgs.length - 1].role === 'assistant') msgs.pop();
          msgs.push(assistantMsg);
          return { ...prev, [threadId]: msgs };
        });
      }

      setToolMapByThread(prev => {
        const map = new Map(prev[threadId] || []);
        const msgs = messagesByThread[threadId] || [];
        const assistantIdx = isRegenerate
          ? (messagesByThread[threadId]?.filter(m => m.role !== 'assistant').length || 0)
          : msgs.length + 1;
        map.set(assistantIdx, []);
        return { ...prev, [threadId]: map };
      });
    }

    setStreaming(true);
    const ac = new AbortController();
    abortRef.current = ac;

    // approval 恢复时从已有 content 继续追加（之前流中的 token 已写入）
    let accumulated = approval
      ? (messagesByThread[threadId]?.[messagesByThread[threadId].length - 1]?.content || '')
      : '';
    let currentTool: ToolCallInfo | null = null;
    const assistantMsgIdx = approval
      ? (messagesByThread[threadId]?.length ? messagesByThread[threadId].length - 1 : 0)
      : isRegenerate
        ? (messagesByThread[threadId]?.filter(m => m.role !== 'assistant').length || 0)
        : (messagesByThread[threadId]?.length || 0) + 1;

    let approvalNeeded = false;
    let pendingToolNames: string[] = [];

    try {
      const stream = isRegenerate
        ? regenerateStream({ threadId, signal: ac.signal })
        : openSessionStream({ content: text, threadId, approval, signal: ac.signal });

      for await (const event of stream) {
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
              const existing = map.get(assistantMsgIdx) || [];
              map.set(assistantMsgIdx, [...existing, tool]);
              return { ...prev, [threadId]: map };
            });
            break;
          }

          case 'tool_end':
            if (currentTool && currentTool.name === event.tool) {
              currentTool.status = 'done';
              currentTool.output = event.output;
              setToolMapByThread(prev => {
                const map = new Map(prev[threadId] || []);
                const arr = (map.get(assistantMsgIdx) || []).map(t =>
                  t.id === currentTool!.id ? { ...currentTool! } : t);
                map.set(assistantMsgIdx, arr);
                return { ...prev, [threadId]: map };
              });
              currentTool = null;
            }
            break;

          case 'intent':
            break;

          case 'tool_approval_needed':
            // 标记需要审批，提取工具名称供弹窗展示
            approvalNeeded = true;
            pendingToolNames = (event.tool_calls || []).map(tc => tc.name);
            ac.abort(); // 中止当前流，等用户决策后恢复
            break;

          case 'error':
            if (!approvalNeeded) {
              showToast(`对话出错：${event.message}`, 'error');
            }
            break;

          case 'done': {
            // 渲染引用卡片
            const cited = event.cited_pages;
            if (cited && cited.length > 0) {
              const citations: CitationInfo[] = cited.map((cp: CitedPage) => ({
                page_id: cp.path,
                title: cp.title,
                path: cp.path,
              }));
              setCitationsByThread(prev => ({
                ...prev,
                [threadId]: new Map([[assistantMsgIdx, citations]]),
              }));
            }
            // 刷新会话列表（标题/消息数由后端生成）
            listRefreshTimer.current = window.setTimeout(() => refreshThreads(true), 800);
            break;
          }
        }
      }
    } catch (err: unknown) {
      // AbortError 在审批场景是预期行为，不弹错误
      if ((err as Error)?.name === 'AbortError' && approvalNeeded) {
        // 审批中断，下面处理
      } else if ((err as Error)?.name === 'AbortError') {
        showToast('已停止生成', 'info');
      } else {
        const message = err instanceof Error ? err.message : String(err);
        showToast(`连接失败：${message}`, 'error');
      }
    } finally {
      if (!approvalNeeded) {
        setStreaming(false);
      }
      abortRef.current = null;
    }

    // ── 审批弹窗 ──
    if (approvalNeeded) {
      const toolList = pendingToolNames.length > 0
        ? pendingToolNames.join('、')
        : '外部工具';
      const approved = await showConfirm(
        `AI 请求调用工具「${toolList}」来搜索知识库，是否允许？`,
        { title: '工具调用审批', confirmLabel: '允许', cancelLabel: '拒绝' },
      );
      // 递归带 approval 恢复
      await streamReply('', threadId, isRegenerate, { approved });
    }
  }, [messagesByThread, refreshThreads]);

  const send = useCallback(async () => {
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
    await streamReply(text, sid, false);
  }, [input, streaming, activeId, streamReply]);

  const handleStop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const handleRegenerate = useCallback(async () => {
    if (!activeId || streaming) return;
    setInput('');
    const lastUserMsg = [...(messagesByThread[activeId] || [])].reverse().find(m => m.role === 'user');
    await streamReply(lastUserMsg?.content || '', activeId, true);
  }, [activeId, streaming, messagesByThread, streamReply]);

  const handleFeedback = useCallback(async (messageIdx: number, rating: 'positive' | 'negative') => {
    if (!activeId) return;
    try {
      await submitFeedback(activeId, messageIdx, rating);
      showToast(rating === 'positive' ? '感谢反馈 👍' : '已记录反馈', 'success');
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      showToast(`反馈失败：${message}`, 'error');
    }
  }, [activeId]);

  // 按厂商分组模型
  const modelGroups = models.reduce<Record<string, ModelInfo[]>>((acc, m) => {
    (acc[m.provider] = acc[m.provider] || []).push(m);
    return acc;
  }, {});

  // ── 计算属性 ──────────────────────────────────────────────────────────
  const active = threads.find(t => t.thread_id === activeId);
  const activeMessages = messagesByThread[activeId] || (activeId ? undefined : []) || [];
  const activeTools = toolMapByThread[activeId] || new Map();
  const activeCitations = citationsByThread[activeId] || new Map();
  const hasActive = activeMessages.length > 0;
  const currentModel = models.find(m => m.id === currentModelId);

  const placeholderText = '输入消息... (Enter 发送，Shift+Enter 换行)';

  // ── 渲染 ──────────────────────────────────────────────────────────────
  return (
    <div
      className={`flex flex-1 min-h-0 transition-all duration-300 ease-out ${
        pageVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-2'
      }`}
    >
      {/* 会话侧栏 */}
      <div
        className={`flex-shrink-0 transition-all duration-200 overflow-hidden ${
          sidebarOpen ? 'w-[260px]' : 'w-0'
        }`}
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

      {/* 折叠按钮 */}
      <div
        className="flex items-center cursor-pointer flex-shrink-0 w-5 border-r border-border justify-center hover:bg-accent/50 transition-colors"
        onClick={() => setSidebarOpen(!sidebarOpen)}
        title={sidebarOpen ? '收起侧栏' : '展开侧栏'}
      >
        <span className="text-[10px] text-muted-foreground">{sidebarOpen ? '◀' : '▶'}</span>
      </div>

      {/* 主聊天区 */}
      <div className="flex-1 flex flex-col min-w-0">
        {hasActive ? (
          <>
            {/* 顶部状态栏 */}
            <div className="border-b border-border bg-card/80 backdrop-blur-sm px-5 py-2.5 flex items-center gap-3 flex-shrink-0">
              <MessageSquare className="h-4 w-4 text-muted-foreground flex-shrink-0" />
              <span className="text-sm font-medium truncate flex-1">
                {active?.title || '新对话'}
              </span>

              {/* 模型选择 */}
              {models.length > 0 && (
                <DropdownMenu>
                  <DropdownMenuTrigger
                    render={
                      <button className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-muted/60 hover:bg-muted text-xs text-muted-foreground transition-colors press">
                        <span className="truncate max-w-[140px]">{currentModel?.display_name || '选择模型'}</span>
                        <ChevronDown className="h-3 w-3 flex-shrink-0" />
                      </button>
                    }
                  />
                  <DropdownMenuContent align="end" className="w-64">
                    <DropdownMenuLabel>选择模型</DropdownMenuLabel>
                    {Object.entries(modelGroups).map(([provider, groupModels], i) => (
                      <div key={provider}>
                        {i > 0 && <div className="my-1 h-px bg-border/60" />}
                        <div className="px-2 py-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/70">
                          {provider === 'deepseek' ? 'DeepSeek' : provider === 'doubao' ? '字节跳动' : provider}
                        </div>
                        {groupModels.map(m => (
                          <DropdownMenuItem
                            key={m.id}
                            onClick={() => {
                              setCurrentModelId(m.id);
                              showToast(`已切换到 ${m.display_name}`, 'info');
                            }}
                            className={currentModelId === m.id ? 'bg-accent font-medium' : ''}
                          >
                            {m.display_name}
                            {m.is_active && <span className="ml-auto text-[10px] text-muted-foreground">默认</span>}
                          </DropdownMenuItem>
                        ))}
                      </div>
                    ))}
                  </DropdownMenuContent>
                </DropdownMenu>
              )}

              <button
                className="p-1.5 rounded-md hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors press"
                onClick={handleClearChat}
                title="清空对话"
                disabled={streaming}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* 消息区 */}
            <div className="flex-1 overflow-y-auto overflow-x-hidden">
              <div className="max-w-3xl mx-auto px-4 py-6 space-y-5">
                {activeMessages.map((msg, idx) => (
                  <ChatMessage
                    key={`${activeId}-${idx}`}
                    message={msg}
                    toolCalls={msg.role === 'assistant' ? activeTools.get(idx) : undefined}
                    citations={msg.role === 'assistant' ? activeCitations.get(idx) : undefined}
                    isStreaming={streaming && idx === activeMessages.length - 1 && msg.role === 'assistant'}
                    onCopy={() => showToast('已复制', 'success')}
                    onRegenerate={idx === activeMessages.length - 1 && msg.role === 'assistant' ? handleRegenerate : undefined}
                    onNavigate={handleNavigate}
                    onCitationClick={handleCitationClick}
                    onFeedback={msg.role === 'assistant' ? (rating) => handleFeedback(idx, rating) : undefined}
                  />
                ))}
                <div ref={messagesEndRef} />
              </div>
            </div>

            {/* 输入区 */}
            <div className="border-t border-border bg-card/95 backdrop-blur-sm px-4 py-3 flex-shrink-0">
              <div className="max-w-3xl mx-auto">
                <div className="flex gap-2 items-end">
                  <Textarea
                    ref={inputRef}
                    placeholder={placeholderText}
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        send();
                      }
                    }}
                    className="min-h-[2.5rem] max-h-40 resize-none rounded-lg focus-visible:ring-1 focus-visible:ring-ring/60 transition-shadow"
                    rows={1}
                    disabled={streaming}
                  />
                  <Button
                    size="icon"
                    onClick={streaming ? handleStop : send}
                    disabled={!streaming && !input.trim()}
                    className="shrink-0 press"
                  >
                    {streaming ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Send className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              </div>
            </div>
          </>
        ) : (
          /* ── 空状态 ── */
          <div className="flex-1 flex items-center justify-center px-4">
            <div className="text-center max-w-2xl w-full">
              <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-5">
                <MessageSquare className="h-7 w-7 text-primary" />
              </div>

              <h2 className="text-xl font-bold mb-2 tracking-tight">与知识库对话</h2>
              <p className="text-sm text-muted-foreground mb-8 leading-relaxed">
                基于你的 Wiki 内容回答，支持文档溯源跳转
              </p>

              <div className="flex flex-wrap gap-2 justify-center mb-8">
                {SUGGESTIONS.map(s => (
                  <button
                    key={s}
                    disabled={streaming}
                    className="px-3.5 py-2 text-xs rounded-full border border-border bg-secondary/50 text-secondary-foreground hover:bg-accent hover:border-accent-foreground/20 transition-all duration-150 press disabled:opacity-50"
                    onClick={() => {
                      setInput(s);
                      setTimeout(() => inputRef.current?.focus(), 50);
                    }}
                  >
                    {s}
                  </button>
                ))}
              </div>

              <div className="max-w-[680px] mx-auto">
                <div className="flex gap-2 items-end">
                  <Textarea
                    ref={inputRef}
                    placeholder={placeholderText}
                    value={input}
                    onChange={e => setInput(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        send();
                      }
                    }}
                    className="min-h-[3rem] max-h-40 resize-none rounded-lg text-[15px] focus-visible:ring-1 focus-visible:ring-ring/60 transition-shadow"
                    rows={1}
                    autoFocus
                  />
                  <Button
                    size="icon"
                    onClick={send}
                    disabled={!input.trim() || streaming}
                    className="shrink-0 press"
                  >
                    {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
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
