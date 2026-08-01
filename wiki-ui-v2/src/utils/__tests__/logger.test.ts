import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { logError, logWarn, logInfo } from '../logger';

describe('logger', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    vi.spyOn(console, 'info').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it('logError 输出到 console 并批量上报后端日志接口', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
    } as Response);

    logError('TestSource', new Error('boom'));
    logWarn('TestSource', 'warning msg');
    logInfo('TestSource', 'info msg');

    // 触发批量 flush（FLUSH_INTERVAL_MS = 2000）
    await vi.advanceTimersByTimeAsync(2000);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe('/v1/frontend/logs');
    const body = JSON.parse(String(init.body));
    expect(body.entries).toHaveLength(3);
    expect(body.entries[0]).toMatchObject({ level: 'error', source: 'TestSource', message: 'boom' });
    expect(body.entries[1]).toMatchObject({ level: 'warn' });
    expect(body.entries[2]).toMatchObject({ level: 'info' });
  });

  it('非 Error 异常也能提取 message', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      status: 200,
    } as Response);

    logError('TestSource', 'string error');
    await vi.advanceTimersByTimeAsync(2000);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(String(init.body));
    expect(body.entries[0].message).toBe('string error');
  });

  it('上报失败静默吞掉，不抛异常', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('network down'));

    expect(() => logError('TestSource', new Error('boom'))).not.toThrow();
    await vi.advanceTimersByTimeAsync(2000);
    // flush 的 catch 已静默，无异常即通过
  });
});
