import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import HealthPage from '../HealthPage';

const mockHealthData = {
  status: 'ok',
  version: '0.1.0',
  uptime_seconds: 125,
  total_pages: 42,
  graph_nodes: 39,
  graph_edges: 641,
  ingest_queue_pending: 0,
};

describe('HealthPage', () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('初始显示健康检查标题', () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise(() => {}));
    render(<HealthPage />);
    expect(screen.getByText('健康检查')).toBeInTheDocument();
    expect(screen.getByText('系统运行状态和关键指标')).toBeInTheDocument();
  });

  it('加载成功后显示指标卡片', async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockHealthData),
    } as Response);

    render(<HealthPage />);

    // 推进时间让 fetch promise resolve
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    expect(screen.getByText('0.1.0')).toBeInTheDocument();
    expect(screen.getByText('服务正常')).toBeInTheDocument();
    expect(screen.getByText('42')).toBeInTheDocument();
    expect(screen.getByText('39')).toBeInTheDocument();
    expect(screen.getByText(/2m 5s/)).toBeInTheDocument();
    expect(screen.getByText('队列为空')).toBeInTheDocument();
  });

  it('每隔 10 秒轮询一次数据', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockHealthData),
    } as Response);

    render(<HealthPage />);

    // 首次 fetch
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // 推进不到 10s
    await act(async () => { await vi.advanceTimersByTimeAsync(9999); });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // 再推进 1ms → 到 10s，触发轮询
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // 再 10s → 第三次
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('卸载组件时清除定时器', async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockHealthData),
    } as Response);
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval');

    const { unmount } = render(<HealthPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(clearIntervalSpy).not.toHaveBeenCalled();
    unmount();
    expect(clearIntervalSpy).toHaveBeenCalled();
  });

  it('点击刷新按钮触发手动刷新并显示旋转动画', async () => {
    vi.useFakeTimers();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockHealthData),
    } as Response);

    render(<HealthPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const refreshBtn = screen.getByRole('button', { name: /刷新$/ });
    fireEvent.click(refreshBtn);
    expect(screen.getByText('刷新中...')).toBeInTheDocument();

    // 等待 400ms setTimeout(setRefreshing(false))
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(screen.getByText('刷新')).toBeInTheDocument();
  });

  it('轮询失败时静默处理，不切换到错误态', async () => {
    vi.useFakeTimers();
    let callCount = 0;
    vi.spyOn(globalThis, 'fetch').mockImplementation(() => {
      callCount++;
      if (callCount === 1) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockHealthData),
        } as Response);
      }
      return Promise.reject(new Error('Network error'));
    });

    render(<HealthPage />);

    // 首次加载成功
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByText('0.1.0')).toBeInTheDocument();

    // 推进 10s 触发轮询（失败）
    await act(async () => { await vi.advanceTimersByTimeAsync(10_000); });

    // 仍显示正常状态，静默失败
    expect(screen.getByText('服务正常')).toBeInTheDocument();
    expect(screen.queryByText('服务异常')).not.toBeInTheDocument();
  });

  it('首次加载失败时显示错误状态', async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Connection refused'));

    render(<HealthPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('服务异常')).toBeInTheDocument();
    expect(screen.getByText('Connection refused')).toBeInTheDocument();
  });

  it('成功加载后显示上次更新时间戳', async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve(mockHealthData),
    } as Response);

    render(<HealthPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText(/上次更新/)).toBeInTheDocument();
  });

  it('有待处理任务时显示警告态', async () => {
    vi.useFakeTimers();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ ...mockHealthData, ingest_queue_pending: 3 }),
    } as Response);

    render(<HealthPage />);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('等待处理中')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });
});
