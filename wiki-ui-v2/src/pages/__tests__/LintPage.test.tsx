import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import LintPage from '../LintPage';

// Mock showToast — 避免真实 toast 依赖
vi.mock('@/components/shared/Toast', () => ({
  showToast: vi.fn(),
}));

const mockLintData = {
  broken_links: [],
  orphan_pages: [],
  index_gaps: [],
  contradictions: [],
  knowledge_gaps: [],
  shallow_pages: [],
  health_score: 100,
  summary: '知识库状态健康',
};

function mockFetchLint(data = mockLintData, ok = true) {
  return vi.spyOn(globalThis, 'fetch').mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    json: () => Promise.resolve(data),
  } as Response);
}

function renderLint() {
  return render(
    <MemoryRouter>
      <LintPage />
    </MemoryRouter>,
  );
}

describe('LintPage — 局部刷新', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('首次加载显示 skeleton 骨架', () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {}));
    renderLint();

    // 应显示4个 stat card skeleton
    const skeletons = document.querySelectorAll('[data-slot="skeleton"], .bg-\\[hsl\\(var\\(--muted\\)\\)\\]');
    // 至少有 skeleton 元素
    expect(skeletons.length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText('Wiki 健康检查')).toBeInTheDocument();
  });

  it('加载成功后显示数据，不闪屏', async () => {
    mockFetchLint();
    renderLint();

    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    // 评分值和单位分开展示
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.getByText('/100')).toBeInTheDocument();
    expect(screen.getAllByText('知识库状态健康').length).toBeGreaterThanOrEqual(1);
  });

  it('手动刷新时保持旧数据显示，不切回 skeleton', async () => {
    const fetchMock = mockFetchLint();
    renderLint();

    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // 点击刷新按钮
    const refreshBtn = screen.getByRole('button', { name: /刷新检测/ });
    fireEvent.click(refreshBtn);

    // 按钮显示"检查中..."，但旧数据仍然可见（无 skeleton）
    expect(screen.getByText('检查中...')).toBeInTheDocument();
    expect(screen.getByText('100')).toBeInTheDocument(); // 数据还在！

    // 等待刷新完成
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText('刷新检测')).toBeInTheDocument(); // 按钮恢复
  });

  it('显示上次检查时间', async () => {
    mockFetchLint();
    renderLint();

    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText(/上次检查/)).toBeInTheDocument();
  });

  it('30 秒静默轮询，不打扰用户', async () => {
    const fetchMock = mockFetchLint();
    renderLint();

    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // 30 秒内不轮询
    await act(async () => { await vi.advanceTimersByTimeAsync(29_999); });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // 30 秒后触发静默轮询
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('轮询失败时静默处理，不显示错误 toast', async () => {
    const { showToast } = await import('@/components/shared/Toast');
    let callCount = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      callCount++;
      if (callCount === 1) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockLintData),
        } as Response);
      }
      return Promise.reject(new Error('Network error'));
    });

    renderLint();

    // 首次成功
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByText('100')).toBeInTheDocument();

    // 30s 后轮询失败
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });

    // showToast 不应被错误调用（静默失败）
    const errorCalls = (showToast as ReturnType<typeof vi.fn>).mock.calls.filter(
      (c: unknown[]) => c[1] === 'error',
    );
    expect(errorCalls.length).toBe(0);

    // 数据仍然显示
    expect(screen.getByText('100')).toBeInTheDocument();
  });

  it('有问题时显示断链数量和评分', async () => {
    mockFetchLint({
      ...mockLintData,
      health_score: 75,
      broken_links: [{ source_page: 'a.md', broken_target: 'b.md' }],
      summary: '发现 1 个断链',
    });

    renderLint();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('75')).toBeInTheDocument();
    expect(screen.getByText('断链 (1)')).toBeInTheDocument();
  });
});
