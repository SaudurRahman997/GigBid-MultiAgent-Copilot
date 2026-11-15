"use client";
import { useMemo, useState } from "react";
import { api, toError, type ApiError } from "@/lib/api/client";
import type { ApprovalRequest, Claim, EvidenceRef } from "@/lib/types";
import { EvidenceHover } from "./EvidenceHover";
import { Badge, ErrorBox } from "./States";

/** Letter text with every verified claim wrapped in an EvidenceHover. */
export function ClaimText({ text, claims, index }: { text: string; claims: Claim[]; index: Record<string, EvidenceRef> }) {
  const parts: React.ReactNode[] = [];
  let rest = text;
  let key = 0;
  const todo = claims.filter((c) => c.text && text.includes(c.text));
  while (rest) {
    let best: { at: number; claim: Claim } | null = null;
    for (const c of todo) {
      const at = rest.indexOf(c.text);
      if (at >= 0 && (!best || at < best.at)) best = { at, claim: c };
    }
    if (!best) {
      parts.push(rest);
      break;
    }
    parts.push(rest.slice(0, best.at));
    parts.push(<EvidenceHover key={key++} claim={best.claim} index={index} />);
    rest = rest.slice(best.at + best.claim.text.length);
  }
  const unplaced = claims.filter((c) => !todo.includes(c));
  return (
    <div>
      <p className="whitespace-pre-wrap leading-relaxed">{parts}</p>
      {unplaced.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {unplaced.map((c, i) => (
            <li key={i}>
              <EvidenceHover claim={c} index={index} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function wordDiff(a: string, b: string) {
  const A = a.split(/\s+/), B = b.split(/\s+/);
  const n = A.length, m = B.length;
  const dp = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) dp[i][j] = A[i] === B[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const out: { t: "same" | "del" | "add"; w: string }[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (A[i] === B[j]) { out.push({ t: "same", w: A[i] }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) out.push({ t: "del", w: A[i++] });
    else out.push({ t: "add", w: B[j++] });
  }
  while (i < n) out.push({ t: "del", w: A[i++] });
  while (j < m) out.push({ t: "add", w: B[j++] });
  return out;
}

export function ApprovalPanel({ request, index, onDone }: { request: ApprovalRequest; index: Record<string, EvidenceRef>; onDone: () => void }) {
  const [mode, setMode] = useState<"view" | "edit" | "reject">("view");
  const original = request.draft.cover_letter;
  const [text, setText] = useState(original);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError>();
  const diff = useMemo(() => (mode === "edit" && text !== original ? wordDiff(original, text) : []), [mode, text, original]);
  const preview = request.dry_run_preview as { connects_cost?: number; connects_balance?: number; would_send?: unknown };
  const blocked = request.compliance && !request.compliance.allowed;

  async function send(body: { action: "approve" | "edit" | "reject"; edited_text?: string; reason?: string }) {
    setBusy(true);
    setError(undefined);
    const r = await api.POST("/approvals/{thread_id}", { params: { path: { thread_id: request.thread_id } }, body });
    setBusy(false);
    if (r.error || !r.response.ok) setError(toError(r.response.status, r.error));
    else onDone();
  }

  return (
    <section aria-label="Approval" className="card space-y-4" data-testid="approval-panel">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold">Approve {request.kind === "message" ? "reply" : "proposal"}</h2>
        <Badge value="awaiting_approval" />
        <span className="text-xs text-muted">draft v{request.draft.version} · nothing is sent until you approve</span>
      </header>

      {blocked && (
        <div role="alert" className="rounded border border-bad/50 bg-bad/10 p-3 text-sm">
          Compliance blocked this text: {request.compliance!.violations.join(", ")}. Edit it before approving.
        </div>
      )}

      {mode === "edit" ? (
        <div className="space-y-2">
          <label htmlFor="edit-draft" className="text-sm font-medium">Edit draft</label>
          <textarea id="edit-draft" value={text} onChange={(e) => setText(e.target.value)} rows={12} className="input w-full font-mono text-sm" />
          {diff.length > 0 && (
            <div aria-label="Changes" className="rounded border border-line p-2 text-sm leading-relaxed" data-testid="diff">
              {diff.map((d, i) => (
                <span key={i} className={d.t === "add" ? "bg-good/20" : d.t === "del" ? "bg-bad/20 line-through" : ""}>
                  {d.w}{" "}
                </span>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="rounded border border-line p-3">
          <ClaimText text={original} claims={request.draft.claims ?? []} index={index} />
        </div>
      )}

      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        {request.price && (
          <div><dt className="text-muted">Price</dt><dd>${request.price.amount}{request.price.kind === "hourly" ? "/h" : ""} <span className="text-muted">(band {request.price.band[0]}–{request.price.band[1]})</span></dd></div>
        )}
        <div><dt className="text-muted">Connects cost</dt><dd data-testid="connects-cost">{request.price?.connects_cost ?? preview.connects_cost ?? "—"}</dd></div>
        <div><dt className="text-muted">Balance</dt><dd>{preview.connects_balance ?? "—"}</dd></div>
        {request.risk && (
          <div><dt className="text-muted">Risk</dt><dd><Badge value={request.risk.verdict} /> {request.risk.flags.join(", ")}</dd></div>
        )}
      </dl>
      <details className="text-xs">
        <summary className="cursor-pointer text-muted">Dry-run preview (what would be sent)</summary>
        <pre className="overflow-x-auto bg-panel2 p-2 rounded mt-1">{JSON.stringify(request.dry_run_preview, null, 2)}</pre>
      </details>

      {mode === "reject" && (
        <div>
          <label htmlFor="reject-reason" className="text-sm font-medium">Why reject? (used to improve future drafts)</label>
          <input id="reject-reason" value={reason} onChange={(e) => setReason(e.target.value)} className="input w-full" />
        </div>
      )}

      {error && <ErrorBox error={error} />}
      <div className="flex flex-wrap gap-2">
        {mode === "view" && (
          <>
            <button className="btn btn-primary" disabled={busy || !!blocked} onClick={() => send({ action: "approve" })}>Approve &amp; send</button>
            <button className="btn" disabled={busy} onClick={() => setMode("edit")}>Edit</button>
            <button className="btn btn-danger" disabled={busy} onClick={() => setMode("reject")}>Reject</button>
          </>
        )}
        {mode === "edit" && (
          <>
            <button className="btn btn-primary" disabled={busy || !text.trim() || text === original} onClick={() => send({ action: "edit", edited_text: text })}>Save edit &amp; send</button>
            <button className="btn" onClick={() => { setMode("view"); setText(original); }}>Cancel</button>
          </>
        )}
        {mode === "reject" && (
          <>
            <button className="btn btn-danger" disabled={busy || !reason.trim()} onClick={() => send({ action: "reject", reason })}>Confirm reject</button>
            <button className="btn" onClick={() => setMode("view")}>Cancel</button>
          </>
        )}
      </div>
    </section>
  );
}
