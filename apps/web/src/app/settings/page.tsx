"use client";
import { useState } from "react";
import { api, toError, useApi, type ApiError } from "@/lib/api/client";
import { PortfolioUploads } from "@/components/PortfolioUploads";
import { Empty, ErrorBox, Loading } from "@/components/States";

type SavedSearch = { name: string; query?: string | null; category?: string | null; every_minutes: number };
type S = { autonomy: "suggest" | "draft" | "approve_each"; daily_connects_budget: number; max_tokens_per_thread: number; saved_searches: SavedSearch[] };

export default function SettingsPage() {
  const settings = useApi(() => api.GET("/settings"), []);
  const accounts = useApi(() => api.GET("/settings/accounts"), []);
  const memory = useApi(() => api.GET("/memory"), []);
  const [edited, setForm] = useState<S>();
  const form = edited ?? (settings.data as S | undefined);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<ApiError>();

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!form) return;
    const r = await api.PUT("/settings", { body: form });
    if (r.error || !r.response.ok) { setError(toError(r.response.status, r.error)); setSaved(false); }
    else { setError(undefined); setSaved(true); }
  }
  async function forget(namespace: string, key: string) {
    await api.DELETE("/memory/{namespace}/{key}", { params: { path: { namespace, key } } });
    void memory.reload();
  }
  async function disconnect(provider: string) {
    await api.DELETE("/settings/accounts/{provider}", { params: { path: { provider } } });
    void accounts.reload();
  }

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold">Settings</h1>
      {settings.loading && <Loading />}
      {settings.error && <ErrorBox error={settings.error} retry={settings.reload} />}
      {form && (
        <form onSubmit={save} className="card space-y-4" aria-label="Autonomy and budgets">
          <fieldset>
            <legend className="font-semibold mb-1">Autonomy</legend>
            {([["suggest", "Suggest only — analyse jobs, never draft"], ["draft", "Draft proposals, I approve each one"], ["approve_each", "Draft and ask me before every send (default)"]] as const).map(([v, l]) => (
              <label key={v} className="flex items-center gap-2 text-sm py-0.5">
                <input type="radio" name="autonomy" checked={form.autonomy === v} onChange={() => setForm({ ...form, autonomy: v })} /> {l}
              </label>
            ))}
            <p className="text-xs text-muted mt-1">Sending always needs your approval; no setting turns that off.</p>
          </fieldset>
          <div className="grid sm:grid-cols-2 gap-3">
            <label className="text-sm">Daily Connects budget
              <input type="number" min={0} max={500} className="input w-full mt-1" value={form.daily_connects_budget}
                onChange={(e) => setForm({ ...form, daily_connects_budget: Number(e.target.value) })} /></label>
            <label className="text-sm">Max tokens per thread
              <input type="number" min={1000} max={200000} step={1000} className="input w-full mt-1" value={form.max_tokens_per_thread}
                onChange={(e) => setForm({ ...form, max_tokens_per_thread: Number(e.target.value) })} /></label>
          </div>
          <fieldset className="space-y-2">
            <legend className="font-semibold">Saved searches</legend>
            {form.saved_searches.map((s, i) => (
              <div key={i} className="flex flex-wrap gap-2 items-end">
                <label className="text-xs">Name<input className="input block" value={s.name} onChange={(e) => { const x = [...form.saved_searches]; x[i] = { ...s, name: e.target.value }; setForm({ ...form, saved_searches: x }); }} /></label>
                <label className="text-xs">Keywords<input className="input block" value={s.query ?? ""} onChange={(e) => { const x = [...form.saved_searches]; x[i] = { ...s, query: e.target.value }; setForm({ ...form, saved_searches: x }); }} /></label>
                <label className="text-xs">Every (min, ≥30)<input type="number" min={30} className="input block w-24" value={s.every_minutes} onChange={(e) => { const x = [...form.saved_searches]; x[i] = { ...s, every_minutes: Number(e.target.value) }; setForm({ ...form, saved_searches: x }); }} /></label>
                <button type="button" className="btn btn-danger" onClick={() => setForm({ ...form, saved_searches: form.saved_searches.filter((_, j) => j !== i) })}>Remove</button>
              </div>
            ))}
            <button type="button" className="btn" onClick={() => setForm({ ...form, saved_searches: [...form.saved_searches, { name: "new search", query: "", every_minutes: 60 }] })}>Add saved search</button>
          </fieldset>
          {error && <ErrorBox error={error} />}
          <div className="flex items-center gap-3"><button className="btn btn-primary">Save settings</button>{saved && <span role="status" className="text-sm text-good">Saved</span>}</div>
        </form>
      )}

      <PortfolioUploads />

      <section className="card space-y-2" aria-label="Accounts">
        <h2 className="font-semibold">Accounts</h2>
        {(accounts.data ?? []).map((a) => (
          <div key={a.provider} className="flex items-center gap-3 text-sm">
            <span className="capitalize">{a.provider}</span>
            <span className={a.connected ? "text-good" : "text-muted"}>{a.connected ? "connected (token encrypted at rest)" : "not connected"}</span>
            {a.connected && <button className="btn ml-auto" onClick={() => disconnect(a.provider)}>Disconnect</button>}
          </div>
        ))}
        <p className="text-xs text-muted">Upwork is read on a conservative schedule; proposals are only created as drafts after your approval.</p>
      </section>

      <section className="card space-y-2" aria-label="Memory">
        <h2 className="font-semibold">What GigBid remembers</h2>
        <p className="text-xs text-muted">Style rules are learned only after the same edit appears in 3 different threads. Outcomes come only from marketplace events. Delete anything.</p>
        {memory.loading && <Loading />}
        {memory.data && memory.data.length === 0 && <Empty title="Nothing remembered yet" />}
        <ul className="divide-y divide-line">
          {(memory.data ?? []).map((m) => (
            <li key={`${m.namespace}/${m.key}`} className="flex items-start gap-3 py-2 text-sm">
              <span className="text-xs rounded bg-panel2 px-2 py-0.5">{m.namespace}</span>
              <span className="flex-1 break-words">{String((m.value as { rule?: string }).rule ?? JSON.stringify(m.value)).slice(0, 200)}</span>
              <button className="btn btn-danger" onClick={() => forget(m.namespace, m.key)} aria-label={`Delete memory ${m.key}`}>Delete</button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
