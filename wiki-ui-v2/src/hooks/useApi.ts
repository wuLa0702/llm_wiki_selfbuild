import { useEffect, useState } from 'react';
import { fetchJson } from '@/api/client';

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!path) return;
    setLoading(true);
    setError(null);
    fetchJson<T>(path)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [path]);

  return { data, loading, error, refetch: () => {} };
}

export function usePolling<T>(path: string, interval: number) {
  const [data, setData] = useState<T | null>(null);

  useEffect(() => {
    const fetch = () => {
      fetchJson<T>(path).then(setData).catch(() => {});
    };
    fetch();
    const id = setInterval(fetch, interval);
    return () => clearInterval(id);
  }, [path, interval]);

  return data;
}
