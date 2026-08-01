import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { MemoryRouter, useLocation, Routes, Route } from 'react-router-dom';
import HomePage from '../HomePage';

vi.mock('@/api/client', () => ({
  fetchJson: vi.fn(),
  postJson: vi.fn(),
  putJson: vi.fn(),
  deleteJson: vi.fn(),
  patchJson: vi.fn(),
  fetchFresh: vi.fn(),
  prefetch: vi.fn(),
  invalidateCache: vi.fn(),
  default: {},
}));

import { fetchJson } from '@/api/client';

const PAGES = [
  { path: 'wiki/concepts/python.md', title: 'Python 语言', page_type: 'concept', created_at: '2026-08-01 10:00' },
  { path: 'wiki/entities/restful.md', title: 'RESTful API', page_type: 'entity', created_at: '2026-07-30 09:00' },
  { path: 'wiki/sources/guide.md', title: '入门指南', page_type: 'source', created_at: '2026-07-28 08:00' },
];

function mockHomeFetch(brokenLinks = 0, recentPages = PAGES) {
  vi.mocked(fetchJson).mockImplementation((path: string) => {
    if (path === '/v1/pages') return Promise.resolve({ pages: PAGES }) as never;
    if (path.startsWith('/v1/lint')) {
      return Promise.resolve({ broken_links: Array.from({ length: brokenLinks }, (_, i) => ({ id: i })) }) as never;
    }
    if (path.includes('sort=created_at')) return Promise.resolve({ pages: recentPages }) as never;
    return Promise.resolve({ pages: [] }) as never;
  });
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderHome() {
  // 不用 Routes：navigate 到 /wiki、/chat 时无匹配路由会卸载整树，直接 MemoryRouter 包裹
  return render(
    <MemoryRouter>
      <HomePage />
      <LocationProbe />
    </MemoryRouter>,
  );
}

describe('HomePage — 统计与渲染', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('加载中显示 skeleton（不显示数值）', async () => {
    vi.mocked(fetchJson).mockReturnValue(new Promise(() => {}) as never);
    renderHome();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('LLM Wiki')).toBeInTheDocument();
    expect(screen.getAllByRole('heading').length).toBeGreaterThan(0);
  });

  it('加载成功：统计卡 + 快捷入口 + 最近页面 + 系统状态', async () => {
    mockHomeFetch(2);
    renderHome();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    // 统计卡：3 页面 / 1 实体 / 1 概念 / 1 引用源
    expect(screen.getByText('总页面')).toBeInTheDocument();
    expect(screen.getByText('实体')).toBeInTheDocument();
    expect(screen.getByText('概念')).toBeInTheDocument();
    expect(screen.getByText('引用源')).toBeInTheDocument();
    expect(screen.getAllByText('3')[0]).toBeInTheDocument();
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(3);

    // 快捷入口
    expect(screen.getByText('浏览知识库')).toBeInTheDocument();
    expect(screen.getByText('AI 对话')).toBeInTheDocument();
    expect(screen.getByText('图谱探索')).toBeInTheDocument();
    expect(screen.getByText('检索文档')).toBeInTheDocument();

    // 最近页面
    expect(screen.getByText('最近页面')).toBeInTheDocument();
    expect(screen.getByText('Python 语言')).toBeInTheDocument();
    expect(screen.getByText('RESTful API')).toBeInTheDocument();

    // 系统状态：运行中 + 已索引 + 断链
    expect(screen.getByText('后端服务')).toBeInTheDocument();
    expect(screen.getByText('运行中')).toBeInTheDocument();
    expect(screen.getByText('已索引')).toBeInTheDocument();
    expect(screen.getByText('断链')).toBeInTheDocument();
    expect(screen.getAllByText('2').length).toBeGreaterThanOrEqual(1);
  });

  it('断链为 0 时也显示断链行', async () => {
    mockHomeFetch(0);
    renderHome();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('断链')).toBeInTheDocument();
  });

  it('无最近页面时显示空态', async () => {
    mockHomeFetch(0, []);
    renderHome();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('暂无页面')).toBeInTheDocument();
    expect(screen.getByText('导入文档后页面将自动创建')).toBeInTheDocument();
  });

  it('接口失败时容错渲染（不崩溃，统计归零）', async () => {
    vi.mocked(fetchJson).mockRejectedValue(new Error('net') as never);
    renderHome();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('总页面')).toBeInTheDocument();
    // 失败后 catch 返回空数组 → 4 张统计卡都显示 0
    expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(4);
  });

  it('点击快捷入口导航到对应路由', async () => {
    mockHomeFetch();
    renderHome();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByText('浏览知识库'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByTestId('location').textContent).toBe('/wiki');

    fireEvent.click(screen.getByText('AI 对话'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByTestId('location').textContent).toBe('/chat');
  });

  it('点击最近页面导航到 wiki 详情', async () => {
    mockHomeFetch();
    renderHome();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByText('Python 语言'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByTestId('location').textContent).toBe('/wiki');
  });
});
