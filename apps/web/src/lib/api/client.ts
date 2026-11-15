"use client";
// Typed API client generated from the FastAPI schema (`make openapi`). Do not hand-write fetch calls.
import createClient from "openapi-fetch";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { paths } from "./schema";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = createClient<paths>({ baseUrl: API_URL, credentials: "include" });

export type ApiError = { status: number; message: string; degraded?: boolean };

export function toError(status: number, error: unknown): ApiError {
  const detail = (error as { detail?: unknown })?.detail;
  if (detail && typeof detail === "object" && "degraded" in (detail as object)) {
    return { status, message: String((detail as { message?: string }).message ?? "unavailable"), degraded: true };
  }
  return { status, message: typeof detail === "string" ? detail : `request failed (${status})` };
}

type Result<T> = { data?: T; error?: unknown; response: Response };

/** Tiny data hook: loading / error / data / reload, for any generated-client call. */
export function useApi<T>(call: () => Promise<Result<T>>, deps: unknown[] = []) {
  const router = useRouter();
  const key = JSON.stringify(deps);
  const [tick, setTick] = useState(0);
  const [res, setRes] = useState<{ key: string; data?: T; error?: ApiError }>({ key: "" });
  const want = `${key}#${tick}`;
  useEffect(() => {
    let alive = true;
    (async () => {
      let next: { key: string; data?: T; error?: ApiError };
      try {
        const r = await call();
        if (r.response.status === 401 && !window.location.pathname.startsWith("/onboarding")) {
          router.replace("/onboarding");
          return;
        }
        next = r.error !== undefined || !r.response.ok ? { key: want, error: toError(r.response.status, r.error) } : { key: want, data: r.data };
      } catch {
        next = { key: want, error: { status: 0, message: "API unreachable", degraded: true } };
      }
      if (alive) setRes((prev) => ({ ...next, data: next.data ?? (next.error ? undefined : prev.data) }));
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [want]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data: res.data, error: res.key === want ? res.error : undefined, loading: res.key !== want, reload };
}
