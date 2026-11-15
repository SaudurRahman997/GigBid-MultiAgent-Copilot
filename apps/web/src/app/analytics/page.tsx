"use client";
import { api, useApi } from "@/lib/api/client";
import { ErrorBox, Loading } from "@/components/States";

type A = { runs: number; submitted: number; tokens: number; avg_steps: number; by_status: Record<string, number>;
  decisions: Record<string, number>; by_stage: Record<string, number>; evals: Record<string, { overall?: Record<string, unknown>; git_sha?: string }> };

function Bars({ title, data }: { title: string; data: Record<string, number> }) {
  const max = Math.max(1, ...Object.values(data));
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]);
  return (
    <section className="card">
      <h2 className="font-semibold mb-3">{title}</h2>
      {rows.length === 0 ? <p className="text-sm text-muted">No data yet.</p> : (
        <dl className="space-y-2">{rows.map(([k, v]) => (
          <div key={k} className="grid grid-cols-[120px_1fr_40px] items-center gap-2 text-sm">
            <dt className="truncate">{k.replaceAll("_", " ")}</dt>
            <dd className="h-3 rounded bg-panel2" aria-hidden><div className="h-3 rounded bg-accent" style={{ width: `${(v / max) * 100}%` }} /></dd>
            <dd className="text-right tabular-nums">{v}</dd>
          </div>))}
        </dl>)}
    </section>
  );
}

export default function Analytics() {
  const { data, error, loading, reload } = useApi(() => api.GET("/analytics"), []);
  const a = data as A | undefined;
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Analytics</h1>
      {loading && <Loading />}
      {error && <ErrorBox error={error} retry={reload} />}
      {a && (
        <>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {([["Runs", a.runs], ["Submitted", a.submitted], ["Tokens", a.tokens], ["Avg steps", a.avg_steps]] as const).map(([k, v]) => (
              <div key={k} className="card"><p className="text-xs text-muted">{k}</p><p className="text-2xl font-semibold tabular-nums">{v}</p></div>
            ))}
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <Bars title="Decisions" data={a.decisions} />
            <Bars title="Run status" data={a.by_status} />
            <Bars title="Pipeline" data={a.by_stage} />
          </div>
          <section className="card">
            <h2 className="font-semibold mb-2">Offline evaluation (from evals/results)</h2>
            {Object.keys(a.evals).length === 0 ? <p className="text-sm text-muted">No result files.</p> : (
              <div className="overflow-x-auto"><table className="text-sm w-full">
                <thead><tr className="text-left text-muted"><th className="pr-4">Run</th><th className="pr-4">Metrics</th><th>Commit</th></tr></thead>
                <tbody>{Object.entries(a.evals).map(([k, v]) => (
                  <tr key={k} className="border-t border-line align-top"><td className="pr-4 py-1">{k}</td>
                    <td className="pr-4 py-1 font-mono text-xs">{Object.entries(v.overall ?? {}).filter(([, x]) => typeof x === "number").map(([m, x]) => `${m}=${Number(x).toFixed(3)}`).join("  ")}</td>
                    <td className="py-1 font-mono text-xs">{v.git_sha}</td></tr>))}
                </tbody></table></div>)}
          </section>
        </>
      )}
    </div>
  );
}
