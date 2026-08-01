import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import WikiPage from '../WikiPage';

vi.mock('@/components/shared/Toast', () => ({ showToast: vi.fn() }));
vi.mock('@/utils/logger', () => ({ logInfo: vi.fn(), logWarn: vi.fn(), logError: vi.fn() }));

const FILE_TREE = {
  wiki: {
    children: {
      concepts: {
        type: 'directory',
        children: {
          'python.md': { type: 'file' },
        },
      },
      'guide.md': { type: 'file' },
    },
  },
};

const PAGE_CONTENT = {
  content: '# Python 入门\n\nPython 是动态语言。',
  title: 'Python 入门',
  page_type: 'concept',
  created_at: '2026-08-01 10:00:00',
  links: ['concepts/fastapi.md'],
  backlinks: [],
  tags: ['语言', '基础'],
  source_file: 'raw/sources/python.md',
};

type RouteHandler = (url: string, init?: RequestInit) => unknown;

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

function renderWiki(initialPath = '/wiki') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/wiki" element={<WikiPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('WikiPage — 加载与空态', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('无选中页面时显示选择页面空态', async () => {
    mockFetchRoutes({
      '/v1/file-tree': () => FILE_TREE,
    });
    renderWiki();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('选择页面')).toBeInTheDocument();
    expect(screen.getByText('从左侧文件树中选择 Wiki 页面查看内容')).toBeInTheDocument();
  });

  it('知识库为空时提示还没有内容', async () => {
    mockFetchRoutes({
      '/v1/file-tree': () => ({ wiki: { children: {} } }),
    });
    renderWiki();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('知识库还没有内容')).toBeInTheDocument();
  });

  it('文件树加载失败容错（不崩溃，内容区仍显示空态）', async () => {
    mockFetchRoutes({
      '/v1/file-tree': () => { throw new Error('boom'); },
    });
    renderWiki();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('选择页面')).toBeInTheDocument();
  });
});

describe('WikiPage — 页面内容', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('带 path 参数时加载并渲染页面内容', async () => {
    const fetchMock = mockFetchRoutes({
      '/v1/file-tree': () => FILE_TREE,
      '/v1/pages/': () => PAGE_CONTENT,
    });
    renderWiki('/wiki?path=concepts/python.md');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    // 请求去掉 wiki/ 前缀，且 encodeURIComponent 会把 / 编码为 %2F
    expect(fetchMock).toHaveBeenCalledWith('/v1/pages/concepts%2Fpython.md');

    // 「Python 入门」出现两处：页面标题 h1 + Markdown 内容里的 # 标题
    expect(screen.getAllByText('Python 入门').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Python 是动态语言。')).toBeInTheDocument();
    expect(screen.getByText('概念')).toBeInTheDocument(); // page_type badge
    expect(screen.getByText('语言')).toBeInTheDocument();  // tag
    expect(screen.getByText(/创建 2026-08-01/)).toBeInTheDocument();
  });

  it('页面不存在时显示不可用错误态', async () => {
    mockFetchRoutes({
      '/v1/file-tree': () => FILE_TREE,
      '/v1/pages/': () => ({}),
      '/v1/file-content': () => ({ error: '路径越权' }),
    });
    renderWiki('/wiki?path=concepts/missing.md');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('页面不可用')).toBeInTheDocument();
    expect(screen.getByText(/不存在/)).toBeInTheDocument();
  });

  it('点击左侧文件树选择页面', async () => {
    const fetchMock = mockFetchRoutes({
      '/v1/file-tree': () => FILE_TREE,
      '/v1/pages/': () => PAGE_CONTENT,
    });
    renderWiki();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    // 展开目录
    fireEvent.click(screen.getByText('concepts'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    fireEvent.click(screen.getByText('python.md'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(fetchMock).toHaveBeenCalledWith('/v1/pages/concepts%2Fpython.md');
    // 标题 h1 + Markdown 内容标题两处
    expect(screen.getAllByText('Python 入门').length).toBeGreaterThanOrEqual(2);
  });

  it('正向引用链接渲染为可点击 chip', async () => {
    mockFetchRoutes({
      '/v1/file-tree': () => FILE_TREE,
      '/v1/pages/': () => PAGE_CONTENT,
    });
    renderWiki('/wiki?path=concepts/python.md');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText(/正向引用/)).toBeInTheDocument();
    expect(screen.getByText('fastapi')).toBeInTheDocument(); // links chip（去 .md 后缀）
  });
});
