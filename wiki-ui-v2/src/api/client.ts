/**
 * API 客户端 — 带 in-memory 缓存的 HTTP 请求封装
 *
 * 缓存策略: stale-while-revalidate
 * - GET 请求: 先返回缓存数据（即使过期），后台刷新
 * - 写请求 (POST/PUT/DELETE): 自动失效相关 GET 缓存
 * - 默认 TTL: 30秒（可覆盖）
 * - 搜索类请求跳过缓存
 */

import ky from 'ky';

// 子路径部署前缀（构建时由 vite base 注入：生产 '/llm-wiki'，dev 为空）
export const API_PREFIX = import.meta.env.BASE_URL.replace(/\/$/, '');
const p = (path: string) => API_PREFIX + path;

const api = ky.create({
  prefix: '',
  timeout: 30000,
});

// ---------------------------------------------------------------------------
// 缓存层
// ---------------------------------------------------------------------------

interface CacheEntry {
  data: unknown;
  timestamp: number;
  ttl: number;          // 新鲜期 (ms)，期内直接用缓存
  staleTtl: number;     // 过期宽容期 (ms)，期内返回缓存+后台刷新
}

const cache = new Map<string, CacheEntry>();
const inflight = new Map<string, Promise<unknown>>(); // 去重：同一路径同一时间只发一次请求
const DEFAULT_TTL = 30_000;        // 30s 新鲜
const DEFAULT_STALE_TTL = 120_000; // 最多返回 2 分钟前的数据（后台刷新）

/** 从缓存读取，返回 null 表示无缓存 */
function cacheGet<T>(key: string): { data: T; fresh: boolean } | null {
  const entry = cache.get(key);
  if (!entry) return null;
  const age = Date.now() - entry.timestamp;
  if (age < entry.ttl) {
    return { data: entry.data as T, fresh: true };
  }
  if (age < entry.staleTtl) {
    return { data: entry.data as T, fresh: false };
  }
  cache.delete(key);
  return null;
}

function cacheSet(key: string, data: unknown, ttl = DEFAULT_TTL, staleTtl = DEFAULT_STALE_TTL): void {
  cache.set(key, { data, timestamp: Date.now(), ttl, staleTtl });
}

/** 失效匹配路径前缀的缓存 */
export function invalidateCache(pattern?: string): void {
  if (!pattern) { cache.clear(); return; }
  for (const key of cache.keys()) {
    if (key.startsWith(pattern)) cache.delete(key);
  }
}

// ---------------------------------------------------------------------------
// 公开方法
// ---------------------------------------------------------------------------

type FetchOptions = { ttl?: number; staleTtl?: number; skipCache?: boolean };

/**
 * GET 请求 — 带 stale-while-revalidate 缓存
 *
 * 行为:
 * 1. 缓存命中 + 新鲜 → 立即返回
 * 2. 缓存命中 + 过期但宽容期内 → 返回缓存 + 后台触发刷新
 * 3. 无缓存 / 超出宽容期 → 等待网络请求
 */
export async function fetchJson<T>(path: string, options?: FetchOptions): Promise<T> {
  if (!options?.skipCache) {
    const hit = cacheGet<T>(path);
    if (hit) {
      if (hit.fresh) return hit.data;
      // stale-while-revalidate: 返回过期数据，后台刷新
      revalidateAsync(path, options);
      return hit.data;
    }
  }

  // 去重：同一路径已有请求在飞，复用同一个 Promise
  const pending = inflight.get(path) as Promise<T> | undefined;
  if (pending) return pending;

  const promise = (async () => {
    try {
      const res = await api.get(p(path));
      const data: T = await res.json();
      if (!options?.skipCache) {
        cacheSet(path, data, options?.ttl, options?.staleTtl);
      }
      return data;
    } finally {
      inflight.delete(path);
    }
  })();

  inflight.set(path, promise);
  return promise;
}

/** 后台异步刷新缓存 (fire-and-forget) */
function revalidateAsync(path: string, options?: FetchOptions): void {
  fetchJson(path, { ...options, skipCache: true })
    .then(() => { /* fetchJson 已经写入缓存 */ })
    .catch(() => { /* 静默失败，保留过期数据 */ });
}

/**
 * POST 请求 — 自动失效 GET 缓存
 */
export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await api.post(p(path), { json: body });
  invalidateCache(path);  // 失效同一路径的 GET 缓存
  return res.json();
}

/**
 * PUT 请求 — 自动失效 GET 缓存
 */
export async function putJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await api.put(p(path), { json: body });
  invalidateCache(path);
  return res.json();
}

/**
 * PATCH 请求 — 自动失效 GET 缓存
 */
export async function patchJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await api.patch(p(path), { json: body });
  invalidateCache(path);
  return res.json();
}

/**
 * DELETE 请求 — 自动失效 GET 缓存
 */
export async function deleteJson<T>(path: string): Promise<T> {
  const res = await api.delete(p(path));
  // 从路径中提取资源前缀：/v1/privacy/rules/keyword → /v1/privacy/rules
  const base = path.replace(/\/[^/]+$/, '');
  invalidateCache(base);
  return res.json();
}

/**
 * 强刷 — 跳过缓存，强制从服务器拉取并更新缓存
 */
export async function fetchFresh<T>(path: string, options?: FetchOptions): Promise<T> {
  return fetchJson<T>(path, { ...options, skipCache: true });
}

/**
 * 批量预热 — 并行发起 GET 请求填充缓存
 */
export function prefetch(...paths: string[]): void {
  for (const path of paths) {
    fetchJson(path).catch(() => {});
  }
}

export default api;
