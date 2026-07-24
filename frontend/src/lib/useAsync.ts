"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "./api";

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
  /** True when the failure is a dead backend (drives the friendly banner). */
  backendDown: boolean;
  reload: () => void;
}

/**
 * Run an async loader and expose {data, loading, error} so every page renders
 * loading / error / success uniformly. Re-runs whenever `deps` change; `reload`
 * forces a refetch (used after actions like generating a summary).
 */
export function useAsync<T>(
  loader: () => Promise<T>,
  deps: readonly unknown[],
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [nonce, setNonce] = useState(0);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    loader()
      .then((result) => {
        if (!cancelled) setData(result);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setData(null);
        setError(
          err instanceof ApiError
            ? err
            : new ApiError("Something went wrong.", { kind: "http" }),
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  return {
    data,
    loading,
    error,
    backendDown: error?.isBackendDown ?? false,
    reload,
  };
}
