import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import GraphPage from '../GraphPage';

// vis-network 在 jsdom 中无法真实渲染 canvas，mock 掉构造（须用 class 才能 new）
// __instances 记录构造次数供断言（class 不是 spy，无法 toHaveBeenCalled）
vi.mock('vis-network', () => {
  const __instances: unknown[] = [];
  return {
    __instances,
    Network: class MockNetwork {
      once = vi.fn();
      on = vi.fn();
      off = vi.fn();
      setOptions = vi.fn();
      fit = vi.fn();
      destroy = vi.fn();
      selectNodes = vi.fn();
      focus = vi.fn();
      moveTo = vi.fn();
      getScale = vi.fn(() => 1);
      constructor() { __instances.push(this); }
    },
  };
});
vi.mock('vis-data', () => ({
  DataSet: class MockDataSet {
    add = vi.fn();
    remove = vi.fn();
    update = vi.fn();
    get = vi.fn(() => []); // GraphPage 依赖 get() 返回数组做 map/forEach
    clear = vi.fn();
    forEach = vi.fn();
  },
}));

import { Network as VisNetwork, __instances as networkInstances } from 'vis-network';

const GRAPH = {
  nodes: [
    { id: 'concepts/python.md', label: 'Python', group: 'concept', page_type: 'concept', degree: 2 },
    { id: 'concepts/fastapi.md', label: 'FastAPI', group: 'concept', page_type: 'concept', degree: 1 },
    { id: 'entities/http.md', label: 'HTTP', group: 'entity', page_type: 'entity', degree: 1 },
  ],
  edges: [
    { from: 'concepts/python.md', to: 'concepts/fastapi.md', id: 0 },
    { from: 'concepts/python.md', to: 'entities/http.md', id: 1 },
  ],
};

type RouteHandler = (url: string, init?: RequestInit) => unknown;

const DEFAULT_INSIGHTS = {
  summary: { total_surprising: 1, total_gaps: 2 },
  surprising: [],
  gaps: [],
};

function mockGraphFetch(overrides: Partial<Record<string, unknown>> = {}) {
  const routes: Record<string, RouteHandler> = {
    '/v1/graph': () => overrides.graph ?? GRAPH,
    '/v1/communities': () => overrides.communities ?? {},
    '/v1/insights': () => overrides.insights ?? DEFAULT_INSIGHTS,
    '/v1/file-tree': () => ({ wiki: { children: {} } }),
  };
  return vi.spyOn(globalThis, 'fetch').mockImplementation((input: unknown) => {
    const url = typeof input === 'string' ? input : (input as Request).url;
    for (const [prefix, handler] of Object.entries(routes)) {
      if (url.startsWith(prefix)) return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve(handler(url)),
      } as Response);
    }
    return Promise.reject(new Error(`Unmocked fetch: ${url}`));
  });
}

function renderGraph() {
  return render(
    <MemoryRouter>
      <GraphPage />
    </MemoryRouter>,
  );
}

describe('GraphPage — 加载与空态', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('加载中显示骨架与提示', async () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {}) as never);
    renderGraph();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('加载图谱...')).toBeInTheDocument();
  });

  it('图谱为空时显示空态提示', async () => {
    mockGraphFetch({ graph: { nodes: [], edges: [] } });
    renderGraph();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('知识图谱为空')).toBeInTheDocument();
    expect(screen.getByText('导入文档后图谱将自动生成')).toBeInTheDocument();
  });

  it('图谱接口失败时显示错误与重试按钮', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: unknown) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.startsWith('/v1/graph')) return Promise.reject(new Error('无法加载图谱数据'));
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({}),
      } as Response);
    });
    renderGraph();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('无法加载图谱数据')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
  });
});

describe('GraphPage — 正常渲染', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    networkInstances.length = 0; // 模块级数组跨测试累积，清空后再断言
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('加载成功后显示节点/链接计数并构造 vis-network', async () => {
    mockGraphFetch();
    renderGraph();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('知识关系图')).toBeInTheDocument();
    expect(screen.getByText('3/3 页面')).toBeInTheDocument();
    expect(screen.getByText('2 链接')).toBeInTheDocument();
    expect(networkInstances.length).toBe(1); // vis-network 被构造一次
  });

  it('communities 与 insights 请求失败时静默降级，图谱仍正常', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((input: unknown) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.startsWith('/v1/communities') || url.startsWith('/v1/insights')) {
        return Promise.reject(new Error('net'));
      }
      if (url.startsWith('/v1/graph')) {
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve(GRAPH),
        } as Response);
      }
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({ wiki: { children: {} } }),
      } as Response);
    });
    renderGraph();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('3/3 页面')).toBeInTheDocument();
    expect(networkInstances.length).toBe(1);
  });
});
