import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import SearchPage from '../SearchPage';

const RESULT = {
  path: 'raw/sources/python.md',
  title: 'Python 指南',
  snippet: 'Python 是一门动态语言，适合快速开发。',
  score: 0.82,
  raw_score: 12.5,
  search_method: 'bm25',
  match_positions: [
    { section: '概述', snippet: 'Python 简介', line: 5, score: 0.9 },
    { section: '语法', snippet: 'Python 语法基础', line: 42, score: 0.6 },
  ],
};

/** 按 URL 分发 mock：/v1/settings 返回设置（默认语义搜索关闭），其余视为 /v1/search */
function mockFetchRoutes(
  overrides: Record<string, unknown> = {},
  settings: Record<string, unknown> = {},
) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input: unknown) => {
    const url = String(input);
    if (url === '/v1/settings') {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ embedding_enabled: false, ...settings }),
      } as Response);
    }
    return Promise.resolve({
      ok: true,
      status: 200,
      json: () => Promise.resolve({
        results: [RESULT],
        total: 1,
        has_more: false,
        method: 'bm25',
        enabled: true,
        ...overrides,
      }),
    } as Response);
  });
}

function mockSearchResponse(overrides: Record<string, unknown> = {}) {
  return mockFetchRoutes(overrides);
}

/** 等待 /v1/settings 的 effect 完成（fetchFresh 有多层 promise，用宏任务兜底） */
async function flushSettings() {
  await act(async () => { await new Promise(r => setTimeout(r, 0)); });
}

function renderSearch() {
  return render(
    <MemoryRouter>
      <SearchPage />
    </MemoryRouter>,
  );
}

async function doSearch(fetchMock?: ReturnType<typeof vi.spyOn>, text = 'Python') {
  void fetchMock;
  fireEvent.change(screen.getByPlaceholderText('搜索知识库... (Enter 检索)'), { target: { value: text } });
  fireEvent.keyDown(screen.getByPlaceholderText('搜索知识库... (Enter 检索)'), { key: 'Enter' });
  await act(async () => { await Promise.resolve(); });
}

describe('SearchPage — 初始与搜索', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('初始显示空态提示', () => {
    renderSearch();
    expect(screen.getByText('搜索知识库')).toBeInTheDocument();
    expect(screen.getByText(/输入关键词搜索 Wiki 页面/)).toBeInTheDocument();
  });

  it('输入关键词回车搜索：POST body 正确，渲染结果', async () => {
    const fetchMock = mockSearchResponse();
    renderSearch();
    await doSearch(fetchMock);

    const call = fetchMock.mock.calls.find(c => String(c[0]) === '/v1/search');
    expect(call).toBeDefined();
    expect(JSON.parse(String((call![1] as RequestInit).body))).toEqual({
      query: 'Python', k: 10, offset: 0, method: 'bm25',
    });

    expect(screen.getByText('Python 指南')).toBeInTheDocument();
    expect(screen.getByText('raw/sources/python.md')).toBeInTheDocument();
    expect(screen.getByText('82%')).toBeInTheDocument(); // score 0.82 → 82%
  });

  it('搜索关键词在 snippet 中高亮为 mark', async () => {
    mockSearchResponse();
    renderSearch();
    await doSearch();

    // snippet 中关键词被包成 <mark>（精确文本节点 = 1）
    const marks = document.querySelectorAll('mark');
    expect(marks.length).toBeGreaterThanOrEqual(1);
    expect(marks[0].textContent).toBe('Python');
    expect(screen.getAllByText('Python').length).toBeGreaterThanOrEqual(1);
  });

  it('置信度低于 10% 的结果被过滤', async () => {
    const fetchMock = mockSearchResponse({
      results: [
        RESULT,
        { path: 'raw/sources/low.md', title: '低相关', snippet: 'x', score: 0.05 },
      ],
      total: 2,
    });
    renderSearch();
    await doSearch(fetchMock);

    expect(screen.getByText('Python 指南')).toBeInTheDocument();
    expect(screen.queryByText('低相关')).not.toBeInTheDocument();
  });

  it('搜索无结果时回到空态', async () => {
    mockSearchResponse({ results: [], total: 0 });
    renderSearch();
    await doSearch();

    expect(screen.getByText('搜索知识库')).toBeInTheDocument();
  });
});

describe('SearchPage — 多命中展开', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('显示「该文件有 N 处命中」，展开后显示章节与行号', async () => {
    mockSearchResponse();
    renderSearch();
    await doSearch();

    expect(screen.getByText('该文件有 2 处命中')).toBeInTheDocument();

    // 展开多命中详情
    fireEvent.click(screen.getByText('该文件有 2 处命中'));
    await act(async () => { await Promise.resolve(); });

    expect(screen.getByText('概述')).toBeInTheDocument();
    expect(screen.getByText('第 5 行')).toBeInTheDocument();
    expect(screen.getByText('语法')).toBeInTheDocument();
    expect(screen.getByText('第 42 行')).toBeInTheDocument();
    expect(screen.getByText('90%')).toBeInTheDocument();
  });
});

describe('SearchPage — 模式切换与分页', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('语义搜索未开放时，点击向量/混合被拦截并提示，搜索仍用 bm25', async () => {
    const fetchMock = mockSearchResponse(); // settings 默认 embedding_enabled=false
    renderSearch();
    await flushSettings();

    fireEvent.click(screen.getByText('混合搜索'));
    // 提示暂未开放（当前版本），方法不切换
    expect(document.body.textContent).toContain('语义搜索暂未开放');
    // 方法未切换（仍显示 BM25 关键词选中态），搜索请求仍带 bm25
    expect(screen.getByText('BM25 关键词')).toBeInTheDocument();
    await doSearch(fetchMock);

    const call = fetchMock.mock.calls.find(c => String(c[0]) === '/v1/search');
    expect(JSON.parse(String((call![1] as RequestInit).body)).method).toBe('bm25');
  });

  it('超过一页时显示分页并可翻页（offset 递增）', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: unknown, init?: RequestInit) => {
      const body = JSON.parse(String((init as RequestInit | undefined)?.body ?? '{}'));
      const offset = (body as { offset: number }).offset;
      return Promise.resolve({
        ok: true,
        status: 200,
        json: () => Promise.resolve({
          results: offset === 0 ? [RESULT] : [{ ...RESULT, path: 'raw/sources/page2.md', title: '第二页' }],
          total: 15,
          has_more: offset === 0,
          method: 'bm25',
          enabled: true,
        }),
      } as Response);
    });
    renderSearch();
    await doSearch(fetchMock);

    expect(screen.getByText(/第 1\/2 页/)).toBeInTheDocument();
    expect(screen.getByText(/15 条结果/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '下一页' }));
    await act(async () => { await Promise.resolve(); });

    expect(screen.getByText('第二页')).toBeInTheDocument();
    const searchCalls = fetchMock.mock.calls.filter(c => String(c[0]) === '/v1/search');
    expect(JSON.parse(String((searchCalls[1][1] as RequestInit).body)).offset).toBe(10);
  });

  it('有结果时显示置信度图例条', async () => {
    mockSearchResponse();
    renderSearch();
    await doSearch();

    expect(screen.getByText(/高 ≥0.65/)).toBeInTheDocument();
    expect(screen.getByText(/中 0.35–0.65/)).toBeInTheDocument();
    expect(screen.getByText(/低 <0.35/)).toBeInTheDocument();
  });
});
