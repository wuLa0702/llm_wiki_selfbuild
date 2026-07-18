import ky from 'ky';

const api = ky.create({
  prefixUrl: '',
  timeout: 30000,
});

export async function fetchJson<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await api.get(path, options as any);
  return res.json();
}

export async function postJson<T>(path: string, body?: unknown): Promise<T> {
  const res = await api.post(path, { json: body });
  return res.json();
}

export async function deleteJson<T>(path: string): Promise<T> {
  const res = await api.delete(path);
  return res.json();
}

export default api;
