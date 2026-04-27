import { useEffect, useRef, useState } from "react";

export type AsyncState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};

export type AsyncOptions<T = unknown> = {
  cacheKey?: string;
  keepPreviousData?: boolean;
  externalCache?: React.MutableRefObject<Map<string, T>>;
};

export function useAsyncData<T>(
  factory: () => Promise<T>,
  deps: unknown[],
  options?: AsyncOptions<T>,
): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: true, error: null });
  const internalCacheRef = useRef<Map<string, T>>(new Map());
  const cacheRef = (options?.externalCache as React.MutableRefObject<Map<string, T>> | undefined) ?? internalCacheRef;

  useEffect(() => {
    let alive = true;
    const cached = options?.cacheKey ? cacheRef.current.get(options.cacheKey) : undefined;
    if (cached !== undefined) {
      setState({ data: cached, loading: false, error: null });
      return () => {
        alive = false;
      };
    }
    setState((prev) => ({
      data: options?.keepPreviousData ? prev.data : null,
      loading: options?.keepPreviousData ? prev.data == null : true,
      error: null,
    }));
    factory()
      .then((data) => {
        if (!alive) return;
        if (options?.cacheKey) {
          cacheRef.current.set(options.cacheKey, data);
        }
        setState({ data, loading: false, error: null });
      })
      .catch((error: unknown) => {
        if (!alive) return;
        setState((prev) => ({
          data: options?.keepPreviousData ? prev.data : null,
          loading: false,
          error: error instanceof Error ? error.message : "알 수 없는 오류",
        }));
      });
    return () => {
      alive = false;
    };
  }, [...deps, options?.cacheKey, options?.keepPreviousData]);

  return state;
}
