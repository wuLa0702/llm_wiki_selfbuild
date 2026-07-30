/**
 * Agent 聊天相关 API 封装
 *
 * 提供：
 *   - 会话 CRUD：listThreads / getThread / renameThread / deleteThread
 *   - SSE 流式对话：openSessionStream（支持 AbortController 中断）
 *
 * 所有 REST 接口复用 client.ts 的 ky 实例 + 缓存失效逻辑；
 * SSE 流独立用 fetch（需直接读 ReadableStream）。
 */

import api, { fetchJson, deleteJson, patchJson, invalidateCache } from './client';

// ── 类型定义 ────────────────────────────────────────────────────────────────

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;
  tool_calls?: ToolCall[];
  tool_call_id?: string;
  name?: string;
}

export interface ToolCall {
  id: string;
  type: 'function';
  function: {
    name: string;
    arguments: string; // JSON 字符串
  };
}

export interface ThreadMeta {
  thread_id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
}

export interface ThreadDetail {
  thread_id: string;
  title: string;
  created_at: number;
  updated_at: number;
  messages: ChatMessage[];
  attention_sinks: unknown[];
  working_memory: Record<string, unknown>;
}

// ── SSE 事件类型 ────────────────────────────────────────────────────────────

export interface SseToken { type: 'token'; content: string }
export interface SseToolStart { type: 'tool_start'; tool: string; input: Record<string, unknown> }
export interface SseToolEnd { type: 'tool_end'; tool: string; output: string }
export interface SseApprovalNeeded {
  type: 'tool_approval_needed';
  tool: string;
  input: Record<string, unknown>;
  tool_call_id: string;
}
export interface SseDone { type: 'done'; sources?: string[] }
export interface SseError { type: 'error'; message: string }

export type AgentSseEvent =
  | SseToken
  | SseToolStart
  | SseToolEnd
  | SseApprovalNeeded
  | SseDone
  | SseError;

// ── REST 接口 ───────────────────────────────────────────────────────────────

const THREADS_PREFIX = '/v1/agent/threads';

/** 获取会话列表（按更新时间倒序） */
export async function listThreads(limit = 50, offset = 0): Promise<ThreadMeta[]> {
  const data = await fetchJson<{ threads: ThreadMeta[] }>(
    `${THREADS_PREFIX}?limit=${limit}&offset=${offset}`,
  );
  return data.threads;
}

/** 获取单个会话详情（含完整消息历史） */
export async function getThread(threadId: string): Promise<ThreadDetail> {
  return fetchJson<ThreadDetail>(`${THREADS_PREFIX}/${threadId}`, { skipCache: false });
}

/** 重命名会话 */
export async function renameThread(threadId: string, title: string): Promise<{ status: string; thread_id: string; title: string }> {
  const body = { title: title.trim() };
  const result = await patchJson<{ status: string; thread_id: string; title: string }>(
    `${THREADS_PREFIX}/${threadId}`,
    body,
  );
  invalidateCache(THREADS_PREFIX);
  return result;
}

/** 删除会话 */
export async function deleteThread(threadId: string): Promise<{ status: string; thread_id: string }> {
  const result = await deleteJson<{ status: string; thread_id: string }>(
    `${THREADS_PREFIX}/${threadId}`,
  );
  invalidateCache(THREADS_PREFIX);
  return result;
}

// ── SSE 流式对话 ────────────────────────────────────────────────────────────

export interface StreamOptions {
  content: string;
  threadId: string;
  approval?: { approved: boolean; [k: string]: unknown };
  signal?: AbortSignal;
}

/**
 * 打开 /v1/agent/chat/session SSE 流，返回 AsyncGenerator 逐事件 yield。
 *
 * 用法：
 *   const ac = new AbortController();
 *   for await (const ev of openSessionStream({ content, threadId, signal: ac.signal })) {
 *     if (ev.type === 'token') append(ev.content);
 *   }
 *   // 中断：ac.abort()
 */
export async function* openSessionStream(opts: StreamOptions): AsyncGenerator<AgentSseEvent> {
  const { content, threadId, approval, signal } = opts;

  const res = await api.post('/v1/agent/chat/session', {
    json: { content, thread_id: threadId, approval },
    signal,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error((err as { error?: string }).error || `HTTP ${res.status}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error('Response body is null');

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data: AgentSseEvent = JSON.parse(line.slice(6));
          yield data;
        } catch {
          // 忽略解析错误（可能是半条消息）
        }
      }
    }
  } finally {
    try { reader.releaseLock(); } catch { /* noop */ }
  }
}
