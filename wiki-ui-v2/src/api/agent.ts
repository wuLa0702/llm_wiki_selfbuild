/**
 * Agent 聊天相关 API 封装
 *
 * 提供：
 *   - 模型列表：listModels
 *   - 会话 CRUD：listThreads / getThread / renameThread / deleteThread / clearThread
 *   - 对话操作：regenerateThread（SSE） / submitFeedback
 *   - SSE 流式对话：openSessionStream（支持 AbortController 中断）
 */

import api, { fetchJson, deleteJson, patchJson, postJson, invalidateCache } from './client';

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

// ── 模型相关 ────────────────────────────────────────────────────────────────

export interface ModelInfo {
  id: string;
  display_name: string;
  provider: string;
  capabilities: string[];
  is_active: boolean;
  configured: boolean;
}

export interface ModelsResponse {
  status: string;
  current: { id: string; provider: string };
  models: ModelInfo[];
}

// ── 引用（cited_pages） ─────────────────────────────────────────────────────

export interface CitedPage {
  path: string;
  title: string;
  page_type: string;
}

// ── SSE 事件类型 ────────────────────────────────────────────────────────────

export interface SseToken { type: 'token'; content: string }
export interface SseIntent { type: 'intent'; intent: string; category?: string }
export interface SseToolStart { type: 'tool_start'; tool: string; input: Record<string, unknown> }
export interface SseToolEnd { type: 'tool_end'; tool: string; output: string }
export interface ApprovalToolCall {
  name: string;
  arguments: string;
  id?: string;
}

export interface SseApprovalNeeded {
  type: 'tool_approval_needed';
  tool_calls: ApprovalToolCall[];
}
export interface SseDone {
  type: 'done';
  sources?: string[];
  cited_pages?: CitedPage[];
  follow_up_questions?: string[];
}
export interface SseError { type: 'error'; message: string }

export type AgentSseEvent =
  | SseToken
  | SseIntent
  | SseToolStart
  | SseToolEnd
  | SseApprovalNeeded
  | SseDone
  | SseError;

// ── REST 接口 ───────────────────────────────────────────────────────────────

const THREADS_PREFIX = '/v1/agent/threads';

/** 获取可用模型列表 */
export async function listModels(): Promise<ModelsResponse> {
  return fetchJson<ModelsResponse>('/v1/agent/models', { skipCache: true });
}

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

/** 清空会话消息（保留线程本身和标题） */
export async function clearThread(threadId: string): Promise<{ status: string; thread_id: string; action: string; messages_removed: number }> {
  const result = await postJson<{ status: string; thread_id: string; action: string; messages_removed: number }>(
    `${THREADS_PREFIX}/${threadId}/clear`,
  );
  invalidateCache(THREADS_PREFIX);
  return result;
}

/** 提交反馈（点赞/点踩） */
export async function submitFeedback(
  threadId: string,
  messageIndex: number,
  rating: 'positive' | 'negative',
  comment = '',
): Promise<{ status: string; thread_id: string; recorded: boolean }> {
  return postJson(`${THREADS_PREFIX}/${threadId}/feedback`, {
    message_index: messageIndex,
    rating,
    comment,
  });
}

// ── SSE 流式对话 ────────────────────────────────────────────────────────────

export interface StreamOptions {
  content: string;
  threadId: string;
  approval?: { approved: boolean; [k: string]: unknown };
  signal?: AbortSignal;
}

export interface ApprovalStreamOptions {
  threadId: string;
  approval: { approved: boolean; [k: string]: unknown };
  signal?: AbortSignal;
}

export interface RegenerateOptions {
  threadId: string;
  signal?: AbortSignal;
}

/**
 * 打开 /v1/agent/chat/session SSE 流，返回 AsyncGenerator 逐事件 yield。
 * 支持审批恢复：传 approval 时 content 可为空字符串。
 */
export async function* openSessionStream(opts: StreamOptions): AsyncGenerator<AgentSseEvent> {
  const { content, threadId, approval, signal } = opts;

  // 注意：审批恢复场景 content 为空字符串 ''，必须保留在 body 里
  // 后端契约：有 approval 时允许空 content；无 approval 时必填
  const body: Record<string, unknown> = {
    thread_id: threadId,
    content: content ?? '',
  };
  if (approval) body.approval = approval;

  const res = await api.post('/v1/agent/chat/session', {
    json: body,
    signal,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error((err as { error?: string }).error || `HTTP ${res.status}`);
  }

  yield* consumeSseStream(res);
}

/**
 * 重新生成上一条助手回复 — SSE 流式
 */
export async function* regenerateStream(opts: RegenerateOptions): AsyncGenerator<AgentSseEvent> {
  const { threadId, signal } = opts;

  const res = await api.post(`${THREADS_PREFIX}/${threadId}/regenerate`, {
    json: {},
    signal,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error((err as { error?: string }).error || `HTTP ${res.status}`);
  }

  yield* consumeSseStream(res);
}

/** 通用 SSE 流消费者 */
async function* consumeSseStream(res: Response): AsyncGenerator<AgentSseEvent> {
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
          // 忽略半条消息解析错误
        }
      }
    }
  } finally {
    try { reader.releaseLock(); } catch { /* noop */ }
  }
}
