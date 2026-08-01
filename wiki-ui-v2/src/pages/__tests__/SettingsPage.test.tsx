import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, act, fireEvent } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import SettingsPage from '../SettingsPage';

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
vi.mock('@/components/shared/Toast', () => ({ showToast: vi.fn() }));
vi.mock('@/components/ui/confirm-dialog', () => ({ showConfirm: vi.fn() }));
vi.mock('@/utils/logger', () => ({ logInfo: vi.fn(), logWarn: vi.fn(), logError: vi.fn() }));

import { fetchJson, postJson } from '@/api/client';
import { showToast } from '@/components/shared/Toast';
import { showConfirm } from '@/components/ui/confirm-dialog';

const DEFAULT_SETTINGS = {
  llm_provider: 'deepseek',
  deepseek_api_key: '',
  deepseek_model: 'deepseek-v4-flash',
  output_language: 'zh',
  search_method: 'bm25',
  theme: 'light',
  privacy_enabled: false,
  watcher_enabled: false,
  watcher_auto_extract: true,
  watcher_poll_interval: 10,
  watcher_max_file_size_mb: 100,
  watcher_allowed_extensions: '',
  watcher_exclude_folders: '',
  watcher_exclude_extensions: '',
  watcher_exclude_patterns: '',
};

function renderTab(tab: string) {
  return render(
    <MemoryRouter initialEntries={[`/settings/${tab}`]}>
      <Routes>
        <Route path="/settings/:tab?" element={<SettingsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('SettingsPage — 数据管理（重置数据文件双重确认）', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(fetchJson).mockResolvedValue(DEFAULT_SETTINGS as never);
    vi.mocked(postJson).mockResolvedValue({ status: 'ok' } as never);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('初始渲染：删除/保留双卡片 + 重置按钮', async () => {
    renderTab('data');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    // 「数据管理」出现两处：侧边 tab 按钮 + 页面标题
    expect(screen.getAllByText('数据管理').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('🗑️ 将删除')).toBeInTheDocument();
    expect(screen.getByText('✅ 将保留')).toBeInTheDocument();
    // 列表项带「· 」前缀，用正则子串匹配
    expect(screen.getByText(/Wiki 页面与图谱数据/)).toBeInTheDocument();
    expect(screen.getByText(/API 密钥与模型配置/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重置数据文件/ })).toBeInTheDocument();
  });

  it('点击重置 → 确认弹窗通过 → 进入输入「确认」的武装态', async () => {
    vi.mocked(showConfirm).mockResolvedValue(true);
    renderTab('data');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByRole('button', { name: /重置数据文件/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(showConfirm).toHaveBeenCalledWith(
      expect.stringContaining('重置将永久删除所有数据文件'),
      expect.objectContaining({ title: '重置数据文件' }),
    );
    expect(screen.getByText(/危险操作 — 数据删除不可恢复/)).toBeInTheDocument();
    expect(screen.getByPlaceholderText('输入：确认')).toBeInTheDocument();
  });

  it('确认弹窗取消 → 不进入武装态', async () => {
    vi.mocked(showConfirm).mockResolvedValue(false);
    renderTab('data');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByRole('button', { name: /重置数据文件/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.queryByText(/危险操作/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重置数据文件/ })).toBeInTheDocument();
  });

  it('输入非「确认」文本时执行按钮禁用', async () => {
    vi.mocked(showConfirm).mockResolvedValue(true);
    renderTab('data');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByRole('button', { name: /重置数据文件/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    const execBtn = screen.getByRole('button', { name: /执行重置/ });
    expect(execBtn).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('输入：确认'), { target: { value: '确认哦' } });
    expect(execBtn).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('输入：确认'), { target: { value: '确认' } });
    expect(execBtn).toBeEnabled();
  });

  it('输入「确认」后执行 → 调 reset-data 接口 → toast 成功', async () => {
    vi.mocked(showConfirm).mockResolvedValue(true);
    renderTab('data');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByRole('button', { name: /重置数据文件/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.change(screen.getByPlaceholderText('输入：确认'), { target: { value: '确认' } });
    fireEvent.click(screen.getByRole('button', { name: /执行重置/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(postJson).toHaveBeenCalledWith('/v1/system/reset-data');
    expect(showToast).toHaveBeenCalledWith('数据文件已重置，请重启服务', 'success');
    // 执行后回到初始态
    expect(screen.getByRole('button', { name: /重置数据文件/ })).toBeInTheDocument();
  });

  it('Enter 键同样触发执行重置', async () => {
    vi.mocked(showConfirm).mockResolvedValue(true);
    renderTab('data');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByRole('button', { name: /重置数据文件/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.change(screen.getByPlaceholderText('输入：确认'), { target: { value: '确认' } });
    fireEvent.keyDown(screen.getByPlaceholderText('输入：确认'), { key: 'Enter' });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(postJson).toHaveBeenCalledWith('/v1/system/reset-data');
  });

  it('「取消」按钮回到初始态', async () => {
    vi.mocked(showConfirm).mockResolvedValue(true);
    renderTab('data');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByRole('button', { name: /重置数据文件/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByRole('button', { name: /取消/ }));
    expect(screen.getByRole('button', { name: /重置数据文件/ })).toBeInTheDocument();
  });

  it('reset-data 接口失败时 toast 错误', async () => {
    vi.mocked(showConfirm).mockResolvedValue(true);
    vi.mocked(postJson).mockRejectedValue(new Error('conn refused') as never);
    renderTab('data');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByRole('button', { name: /重置数据文件/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    fireEvent.change(screen.getByPlaceholderText('输入：确认'), { target: { value: '确认' } });
    fireEvent.click(screen.getByRole('button', { name: /执行重置/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(showToast).toHaveBeenCalledWith('重置失败，请检查服务', 'error');
  });
});

describe('SettingsPage — 执行日志', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(fetchJson).mockResolvedValue(DEFAULT_SETTINGS as never);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  const mockLogFetch = (content = '') =>
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
      json: () => Promise.resolve({ source: 'backend', content }),
    } as Response);

  it('默认加载后端日志并显示内容', async () => {
    const fetchMock = mockLogFetch('2026-08-01 10:00 ingest done\n');
    renderTab('logs');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(fetchMock).toHaveBeenCalledWith('/v1/logs/tail?source=backend&lines=300');
    expect(screen.getByText('2026-08-01 10:00 ingest done')).toBeInTheDocument();
    expect(screen.getByText(/后端日志/)).toBeInTheDocument();
    expect(screen.getByText(/前端日志/)).toBeInTheDocument();
    expect(screen.getByText('最近 300 行 · 10s 刷新')).toBeInTheDocument();
  });

  it('日志为空时显示占位提示', async () => {
    mockLogFetch('');
    renderTab('logs');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('暂无日志（日志文件不存在或日志未开启）')).toBeInTheDocument();
  });

  it('切换前端日志 source=frontend 并显示', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input: unknown) => {
      const url = String(input);
      if (url.includes('source=frontend')) {
        return Promise.resolve({
          ok: true, status: 200,
          json: () => Promise.resolve({ source: 'frontend', content: '[error] react crashed' }),
        } as Response);
      }
      return Promise.resolve({
        ok: true, status: 200,
        json: () => Promise.resolve({ source: 'backend', content: '' }),
      } as Response);
    });
    renderTab('logs');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    fireEvent.click(screen.getByRole('button', { name: /前端日志/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(fetchMock).toHaveBeenCalledWith('/v1/logs/tail?source=frontend&lines=300');
    expect(screen.getByText('[error] react crashed')).toBeInTheDocument();
  });

  it('10s 自动轮询刷新日志', async () => {
    const fetchMock = mockLogFetch('line1\n');
    renderTab('logs');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(9999); });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('关闭自动刷新后不再轮询', async () => {
    const fetchMock = mockLogFetch('line1\n');
    renderTab('logs');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // 切换 autoRefresh 会触发 effect 重跑（组件预期行为），先记下此时的调用基数
    fireEvent.click(screen.getByText('自动刷新'));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    const afterToggle = fetchMock.mock.calls.length;
    expect(afterToggle).toBe(2); // effect 重跑 → 一次立即加载

    // 之后推进 30s 不再触发轮询
    await act(async () => { await vi.advanceTimersByTimeAsync(30_000); });
    expect(fetchMock).toHaveBeenCalledTimes(afterToggle);
  });
});

describe('SettingsPage — tab 切换', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.mocked(fetchJson).mockResolvedValue(DEFAULT_SETTINGS as never);
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true, status: 200,
      json: () => Promise.resolve({ source: 'backend', content: '' }),
    } as Response);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('从数据管理点击执行日志 tab 切换视图', async () => {
    renderTab('data');
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('🗑️ 将删除')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /执行日志/ }));
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(screen.getByText('查看后端 / 前端运行日志，方便排查导入、队列等问题')).toBeInTheDocument();
    expect(screen.queryByText('🗑️ 将删除')).not.toBeInTheDocument();
  });
});
