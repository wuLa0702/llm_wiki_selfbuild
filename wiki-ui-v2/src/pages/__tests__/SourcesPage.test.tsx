import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SourcesPage from '../SourcesPage';

vi.mock('@/components/shared/Toast', () => ({ showToast: vi.fn() }));
vi.mock('@/components/ui/confirm-dialog', () => ({ showConfirm: vi.fn() }));
vi.mock('@/utils/logger', () => ({ logInfo: vi.fn(), logWarn: vi.fn(), logError: vi.fn() }));

import { showToast } from '@/components/shared/Toast';
import { showConfirm } from '@/components/ui/confirm-dialog';
import { logInfo } from '@/utils/logger';

const TREE = {
  tree: [
    { name: 'guide.md', type: 'file', path: 'raw/sources/guide.md', size: 1234 },
    {
      name: 'notes', type: 'directory', path: 'raw/sources/notes',
      children: [{ name: 'a.md', type: 'file', path: 'raw/sources/notes/a.md', size: 100 }],
    },
  ],
  total_files: 2,
};

type RouteHandler = (url: string, init?: RequestInit) => unknown;

/** 按 URL 前缀分发的 fetch mock；未匹配的 URL 直接 reject（防漏测） */
function mockFetchRoutes(routes: Record<string, RouteHandler>) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input: unknown, init?: RequestInit) => {
    const url = typeof input === 'string' ? input : (input as Request).url;
    for (const [prefix, handler] of Object.entries(routes)) {
      if (url.startsWith(prefix)) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(handler(url, init)),
        } as Response);
      }
    }
    return Promise.reject(new Error(`Unmocked fetch: ${url}`));
  });
}

function makeFile(name: string, content = '# hi', relativePath?: string): File {
  const f = new File([content], name, { type: 'text/markdown' });
  if (relativePath) (f as unknown as { webkitRelativePath: string }).webkitRelativePath = relativePath;
  return f;
}

function renderPage() {
  return render(
    <MemoryRouter>
      <SourcesPage />
    </MemoryRouter>,
  );
}

describe('SourcesPage — 文件树', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('加载成功显示文件与目录，底部显示文件总数', async () => {
    mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => ({ jobs: [] }),
      '/v1/ingest/queue/status': () => ({ total: 0, pending: 0, processing: 0, done: 0, failed: 0, cancelled: 0 }),
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('guide.md')).toBeInTheDocument();
    expect(screen.getByText('notes')).toBeInTheDocument();
    expect(screen.getByText('2 个文件')).toBeInTheDocument();
  });

  it('目录默认收起，点击展开显示子文件', async () => {
    mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => ({ jobs: [] }),
      '/v1/ingest/queue/status': () => ({ total: 0, pending: 0, processing: 0, done: 0, failed: 0, cancelled: 0 }),
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.queryByText('a.md')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('notes'));
    expect(screen.getByText('a.md')).toBeInTheDocument();
  });

  it('树加载失败时 toast 报错', async () => {
    mockFetchRoutes({
      '/v1/sources/tree': () => { throw new Error('boom'); },
      '/v1/ingest/queue/recent': () => ({ jobs: [] }),
      '/v1/ingest/queue/status': () => ({ total: 0, pending: 0, processing: 0, done: 0, failed: 0, cancelled: 0 }),
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(showToast).toHaveBeenCalledWith('加载文件树失败', 'error');
  });
});

describe('SourcesPage — 上传（单文件 / 文件夹分支）', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('单文件上传：文件名入 FormData，成功后 toast 计数文案', async () => {
    const fetchMock = mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => ({ jobs: [] }),
      '/v1/ingest/queue/status': () => ({ total: 0, pending: 0, processing: 0, done: 0, failed: 0, cancelled: 0 }),
      '/v1/ingest/upload': (url, init) => {
        const fd = init?.body as FormData;
        return { saved: fd.getAll('files').length, enqueued: 1, skipped_unchanged: 0 };
      },
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    // 单文件 input（无 webkitdirectory）
    const fileInputs = document.querySelectorAll('input[type="file"]');
    expect(fileInputs.length).toBe(2);
    expect(fileInputs[0].hasAttribute('webkitdirectory')).toBe(false);
    expect(fileInputs[1].hasAttribute('webkitdirectory')).toBe(true);

    fireEvent.change(fileInputs[0], { target: { files: [makeFile('guide.md'), makeFile('b.md')] } });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    const uploadCall = fetchMock.mock.calls.find(c => String(c[0]).startsWith('/v1/ingest/upload'));
    expect(uploadCall).toBeTruthy();
    const fd = uploadCall![1]!.body as FormData;
    expect(fd.getAll('files')).toHaveLength(2);
    expect(showToast).toHaveBeenCalledWith('已上传 2 个文件，1 个已加入队列', 'success');
    expect(logInfo).toHaveBeenCalled();
  });

  it('文件夹上传：使用 webkitRelativePath 保留目录结构', async () => {
    const fetchMock = mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => ({ jobs: [] }),
      '/v1/ingest/queue/status': () => ({ total: 0, pending: 0, processing: 0, done: 0, failed: 0, cancelled: 0 }),
      '/v1/ingest/upload': (url, init) => {
        const fd = init?.body as FormData;
        return { saved: fd.getAll('files').length, enqueued: 2, skipped_unchanged: 0 };
      },
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    const folderInput = document.querySelectorAll('input[type="file"]')[1];
    fireEvent.change(folderInput, {
      target: { files: [makeFile('a.md', '# a', 'notes/a.md')] },
    });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    const uploadCall = fetchMock.mock.calls.find(c => String(c[0]).startsWith('/v1/ingest/upload'));
    const fd = uploadCall![1]!.body as FormData;
    expect(fd.get('files')).toBeInstanceOf(File);
    expect((fd.get('files') as File).name).toBe('notes/a.md');
    expect(showToast).toHaveBeenCalledWith('已上传 1 个文件，2 个已加入队列', 'success');
  });

  it('上传接口返回 error 时 toast 失败文案', async () => {
    mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => ({ jobs: [] }),
      '/v1/ingest/queue/status': () => ({ total: 0, pending: 0, processing: 0, done: 0, failed: 0, cancelled: 0 }),
      '/v1/ingest/upload': () => ({ error: '文件类型不允许' }),
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.change(document.querySelectorAll('input[type="file"]')[0], {
      target: { files: [makeFile('evil.exe')] },
    });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(showToast).toHaveBeenCalledWith('上传失败：文件类型不允许', 'error');
  });
});

describe('SourcesPage — 文件预览（403 错误显示）', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('预览成功：显示内容与大小', async () => {
    mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => ({ jobs: [] }),
      '/v1/ingest/queue/status': () => ({ total: 0, pending: 0, processing: 0, done: 0, failed: 0, cancelled: 0 }),
      '/v1/file-content': () => ({ content: '# 指南内容', size: 200 }),
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByText('guide.md'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    // MarkdownRenderer 将 `# 指南内容` 渲染为 h1 标题
    expect(screen.getByRole('heading', { level: 1, name: '指南内容' })).toBeInTheDocument();
    expect(screen.getByText('200 B')).toBeInTheDocument();
  });

  it('预览返回 403（无 content 字段）时 toast 显示后端错误，不再静默空白', async () => {
    mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => ({ jobs: [] }),
      '/v1/ingest/queue/status': () => ({ total: 0, pending: 0, processing: 0, done: 0, failed: 0, cancelled: 0 }),
      '/v1/file-content': () => ({ error: '路径越权', detail: 'Access denied' }),
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByText('guide.md'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(showToast).toHaveBeenCalledWith('预览失败：路径越权', 'error');
  });
});

describe('SourcesPage — 队列面板', () => {
  const QUEUE = {
    recent: {
      jobs: [
        { job_id: 'j1', source_path: 'raw/sources/guide.md', status: 'processing' },
        { job_id: 'j2', source_path: 'raw/sources/b.md', status: 'pending' },
        { job_id: 'j3', source_path: 'raw/sources/c.md', status: 'failed', error: 'LLM timeout' },
      ],
    },
    status: { total: 3, pending: 1, processing: 1, done: 0, failed: 1, cancelled: 0 },
  };

  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('活跃与失败任务显示 badge，job 列表带状态标签', async () => {
    mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => QUEUE.recent,
      '/v1/ingest/queue/status': () => QUEUE.status,
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('2 活跃')).toBeInTheDocument();
    // 「1 失败」出现两处：header badge + 进度条统计
    expect(screen.getAllByText('1 失败').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('处理中')).toBeInTheDocument();
    expect(screen.getByText('等待中')).toBeInTheDocument();
    // 进度统计：1 处理中 · 0 完成 · 1 失败
    expect(screen.getByText('0 完成')).toBeInTheDocument();
  });

  it('队列面板可折叠展开', async () => {
    mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => QUEUE.recent,
      '/v1/ingest/queue/status': () => QUEUE.status,
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('处理中')).toBeInTheDocument();
    fireEvent.click(screen.getByText('导入队列'));
    expect(screen.queryByText('处理中')).not.toBeInTheDocument();
  });

  it('失败任务重试：点击重试调 retry 接口并 toast', async () => {
    const fetchMock = mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => QUEUE.recent,
      '/v1/ingest/queue/status': () => QUEUE.status,
      '/v1/ingest/queue/retry/j3': () => ({ status: 'ok' }),
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByTitle('重试'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(fetchMock).toHaveBeenCalledWith('/v1/ingest/queue/retry/j3', { method: 'POST' });
    expect(showToast).toHaveBeenCalledWith('已重新加入队列', 'success');
  });

  it('多个失败任务时显示「清空失败记录」与「全部重试」', async () => {
    mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => ({
        jobs: [
          { job_id: 'j1', source_path: 'a.md', status: 'failed' },
          { job_id: 'j2', source_path: 'b.md', status: 'failed' },
        ],
      }),
      '/v1/ingest/queue/status': () => ({ total: 2, pending: 0, processing: 0, done: 0, failed: 2, cancelled: 0 }),
      '/v1/ingest/queue/failed': () => ({ deleted: 2 }),
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByText('清空失败记录'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(showToast).toHaveBeenCalledWith('已清理 2 条失败记录', 'success');
    expect(screen.getByText('全部重试')).toBeInTheDocument();
  });
});

describe('SourcesPage — 删除与提取', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('删除文件：确认后调 DELETE，toast 级联删除数', async () => {
    vi.mocked(showConfirm).mockResolvedValue(true);
    const fetchMock = mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => ({ jobs: [] }),
      '/v1/ingest/queue/status': () => ({ total: 0, pending: 0, processing: 0, done: 0, failed: 0, cancelled: 0 }),
      '/v1/sources/delete': () => ({ status: 'deleted', wiki_pages_deleted: 3 }),
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByTitle('删除'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(showConfirm).toHaveBeenCalled();
    expect(fetchMock).toHaveBeenCalledWith(
      '/v1/sources/delete?path=raw%2Fsources%2Fguide.md',
      { method: 'DELETE' },
    );
    expect(showToast).toHaveBeenCalledWith('已删除，级联删除 3 个页面', 'success');
  });

  it('取消确认时不做删除请求', async () => {
    vi.mocked(showConfirm).mockResolvedValue(false);
    const fetchMock = mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => ({ jobs: [] }),
      '/v1/ingest/queue/status': () => ({ total: 0, pending: 0, processing: 0, done: 0, failed: 0, cancelled: 0 }),
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByTitle('删除'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining('/v1/sources/delete'),
      expect.anything(),
    );
  });

  it('提取：文件未变化 → 确认强制生成 → force=true 重新调用', async () => {
    vi.mocked(showConfirm).mockResolvedValue(true);
    const fetchMock = mockFetchRoutes({
      '/v1/sources/tree': () => TREE,
      '/v1/ingest/queue/recent': () => ({ jobs: [] }),
      '/v1/ingest/queue/status': () => ({ total: 0, pending: 0, processing: 0, done: 0, failed: 0, cancelled: 0 }),
      '/v1/sources/check-changed': () => ({ changed: false }),
      '/v1/sources/extract-to-wiki': (url, init) => {
        const body = JSON.parse(String(init?.body ?? '{}'));
        if (body.force === true) return { status: 'ok', pages_created: ['A'], pages_updated: ['B', 'C'] };
        return { status: 'skipped' };
      },
    });
    renderPage();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByTitle('提取到 Wiki'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    // 未变化 → 确认弹窗（强制生成）
    expect(showConfirm).toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    const forceCall = fetchMock.mock.calls.find(
      c => String(c[0]).startsWith('/v1/sources/extract-to-wiki')
        && JSON.parse(String(c[1]!.body ?? '{}')).force === true,
    );
    expect(forceCall).toBeTruthy();
    expect(showToast).toHaveBeenCalledWith('提取完成：1 创建 · 2 更新', 'success');
  });
});
