/**
 * ChatPage 工具调用流回归测试
 *
 * 背景：tool_end 事件处理曾有一个闭包陷阱 —— setState updater 延迟执行时
 * 读已置 null 的 currentTool.id，导致 Cannot read properties of null (reading 'id')，
 * React 整树卸载 → 对话页白屏（真实线上事故，playwright 已复现）。
 *
 * 本测试锁死该行为：SSE 流发出 tool_start → tool_end 后，页面必须正常渲染
 * 工具调用徽章，且不抛任何渲染错误。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import ChatPage from '../ChatPage';
import type { AgentSseEvent } from '@/api/agent';

// ── mock API 层 ────────────────────────────────────────────────────────────

vi.mock('@/api/agent', () => ({
  listThreads: vi.fn(async () => []),
  getThread: vi.fn(async () => ({
    thread_id: 't1', title: '', created_at: 0, updated_at: 0,
    messages: [], attention_sinks: [], working_memory: {},
  })),
  renameThread: vi.fn(async () => ({ status: 'ok', thread_id: '', title: '' })),
  deleteThread: vi.fn(async () => ({ status: 'ok', thread_id: '' })),
  clearThread: vi.fn(async () => ({ status: 'ok', thread_id: '', action: '', messages_removed: 0 })),
  listModels: vi.fn(async () => ({ status: 'ok', current: { id: 'm1', provider: 'x' }, models: [] })),
  openSessionStream: vi.fn(),
  regenerateStream: vi.fn(),
  submitFeedback: vi.fn(),
}));

vi.mock('@/components/shared/Toast', () => ({ showToast: vi.fn() }));
vi.mock('@/components/ui/confirm-dialog', () => ({ showConfirm: vi.fn(async () => true) }));

import * as agentApi from '@/api/agent';

/** 构造工具调用流：token → tool_start → tool_end → done */
async function* toolStream(): AsyncGenerator<AgentSseEvent> {
  yield { type: 'token', content: '正在搜索' };
  yield { type: 'tool_start', tool: 'search_wiki', input: { query: 'LangGraph' } };
  yield { type: 'tool_end', tool: 'search_wiki', output: '找到 3 个结果' };
  yield { type: 'token', content: '，结果如下' };
  yield { type: 'done', sources: [], cited_pages: [], follow_up_questions: [] };
}

/** 渲染 ChatPage（含路由） */
function renderChat() {
  return render(
    <MemoryRouter>
      <ChatPage />
    </MemoryRouter>,
  );
}

describe('ChatPage 工具调用流', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom 缺 scrollIntoView
    if (!Element.prototype.scrollIntoView) {
      Element.prototype.scrollIntoView = () => {};
    }
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('tool_start → tool_end 完整流：渲染工具徽章且不崩溃（回归：null.id 闭包 bug）', async () => {
    vi.mocked(agentApi.openSessionStream).mockImplementationOnce(
      () => toolStream() as AsyncGenerator<AgentSseEvent>,
    );

    renderChat();

    // 输入并发送消息
    const textarea = await screen.findByPlaceholderText(/输入消息/);
    fireEvent.change(textarea, { target: { value: '搜索 LangGraph' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    // 等流式事件处理完 → 工具折叠条出现（hasToolCalls = true）
    const toolBar = await screen.findByText('工具调用');
    expect(toolBar).toBeInTheDocument();

    // 展开 → 工具徽章显示工具中文名（search_wiki → 搜索知识库）
    fireEvent.click(toolBar);
    await waitFor(() => {
      expect(screen.getByText('搜索知识库')).toBeInTheDocument();
    });

    // 页面主体仍然渲染（没有整树卸载白屏）：token 内容 + 输入框都在
    expect(screen.getByText('正在搜索，结果如下')).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/输入消息/)).toBeInTheDocument();
  });

  it('无工具调用的普通流：正常显示回复', async () => {
    vi.mocked(agentApi.openSessionStream).mockImplementationOnce(
      function* () {
        yield { type: 'token', content: '你好' };
        yield { type: 'done', sources: [], cited_pages: [], follow_up_questions: [] };
      } as () => AsyncGenerator<AgentSseEvent>,
    );

    renderChat();

    const textarea = await screen.findByPlaceholderText(/输入消息/);
    fireEvent.change(textarea, { target: { value: '你好' } });
    fireEvent.keyDown(textarea, { key: 'Enter' });

    await waitFor(() => {
      expect(screen.getByText(/你好/)).toBeInTheDocument();
    });
  });
});
