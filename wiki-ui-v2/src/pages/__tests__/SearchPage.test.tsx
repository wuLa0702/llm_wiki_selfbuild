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

function mockSearchResponse(overrides: Record<string, unknown> = {}) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue({
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

    const call = fetchMock.mock.calls[0];
    expect(call[0]).toBe('/v1/search');
    expect(JSON.parse(String((call[1] as RequestInit).body))).toEqual({
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

  it('切换到 hybrid 后搜索请求带 method=hybrid', async () => {
    const fetchMock = mockSearchResponse({ method: 'hybrid' });
    renderSearch();

    // 初始按钮显示当前模式：BM25 关键词；点击切换为混合搜索
    fireEvent.click(screen.getByText('BM25 关键词'));
    expect(screen.getByText('混合搜索')).toBeInTheDocument();
    await doSearch(fetchMock);

    const call = fetchMock.mock.calls[0];
    expect(JSON.parse(String((call[1] as RequestInit).body)).method).toBe('hybrid');
  });

  it('超过一页时显示分页并可翻页（offset 递增）', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: unknown, init?: RequestInit) => {
      const body = JSON.parse(String((init as RequestInit).body ?? '{}'));
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
    const secondCall = fetchMock.mock.calls[1];
    expect(JSON.parse(String((secondCall[1] as RequestInit).body)).offset).toBe(10);
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
