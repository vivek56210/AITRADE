import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Poll an async fetcher on an interval. Interval ticks never overlap a request in flight; a change of deps
 * always fetches immediately and any older response that lands afterwards is discarded.
 * Returns data, error and a manual refresh.
 */
export function usePoll<T>(fetcher: () => Promise<T>, intervalMs: number, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inflight = useRef(false);
  const seq = useRef(0);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  const load = useCallback(async (force: boolean) => {
    if (inflight.current && !force) return;
    const mine = ++seq.current;
    inflight.current = true;
    try {
      const result = await fetcherRef.current();
      if (mine === seq.current) {
        setData(result);
        setError(null);
      }
    } catch (e) {
      if (mine === seq.current) setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (mine === seq.current) inflight.current = false;
    }
  }, []);

  const refresh = useCallback(() => load(false), [load]);

  useEffect(() => {
    void load(true);
    if (intervalMs <= 0) return;
    const id = window.setInterval(() => void load(false), intervalMs);
    return () => window.clearInterval(id);
  }, [load, intervalMs, ...deps]);

  return { data, error, refresh, setData };
}
