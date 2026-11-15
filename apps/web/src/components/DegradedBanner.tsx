"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";

/** Shown when the marketplace MCP server (or the API) is unreachable. Writes are queued, not lost. */
export function DegradedBanner() {
  const [degraded, setDegraded] = useState(false);
  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const { data } = await api.GET("/health");
        if (alive) setDegraded(Boolean(data?.degraded));
      } catch {
        if (alive) setDegraded(true);
      }
    };
    void check();
    const t = setInterval(check, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  if (!degraded) return null;
  return (
    <div role="alert" data-testid="degraded-banner" className="bg-warn text-black text-sm px-4 py-2 text-center">
      Marketplace unavailable — showing saved data. Approved actions are queued and will be sent when it is back.
    </div>
  );
}
