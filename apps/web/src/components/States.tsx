import type { ApiError } from "@/lib/api/client";

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="animate-pulse text-sm text-muted py-8 text-center">
      {label}…
    </div>
  );
}

export function Empty({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-line p-8 text-center">
      <p className="font-medium">{title}</p>
      {hint && <p className="text-sm text-muted mt-1">{hint}</p>}
    </div>
  );
}

export function ErrorBox({ error, retry }: { error: ApiError; retry?: () => void }) {
  return (
    <div role="alert" className="rounded-lg border border-bad/40 bg-bad/10 p-4 text-sm">
      <p className="font-medium">{error.degraded ? "Marketplace unavailable" : "Something went wrong"}</p>
      <p className="text-muted">{error.message}</p>
      {retry && (
        <button onClick={retry} className="btn mt-2">
          Try again
        </button>
      )}
    </div>
  );
}

const TONE: Record<string, string> = {
  submitted: "bg-good/15 text-good",
  done: "bg-good/15 text-good",
  sent: "bg-good/15 text-good",
  awaiting_approval: "bg-warn/15 text-warn",
  running: "bg-accent/15 text-accent",
  resuming: "bg-accent/15 text-accent",
  queued: "bg-accent/15 text-accent",
  skipped: "bg-line text-muted",
  watch: "bg-line text-muted",
  rejected: "bg-bad/15 text-bad",
  blocked: "bg-bad/15 text-bad",
  error: "bg-bad/15 text-bad",
  needs_attention: "bg-bad/15 text-bad",
  dead_letter: "bg-bad/15 text-bad",
  bid: "bg-good/15 text-good",
  skip: "bg-line text-muted",
  block: "bg-bad/15 text-bad",
  caution: "bg-warn/15 text-warn",
  ok: "bg-good/15 text-good",
};

export function Badge({ value }: { value?: string | null }) {
  if (!value) return null;
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${TONE[value] ?? "bg-line text-muted"}`}>
      {value.replaceAll("_", " ")}
    </span>
  );
}
