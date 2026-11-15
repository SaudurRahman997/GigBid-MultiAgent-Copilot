// Shapes of the graph state the API returns inside `state` / `summary` (dict[str, Any] in OpenAPI).
// They mirror agent/handoffs.py.
export type EvidenceRef = { evidence_id: string; snippet: string; score: number; outcome?: string | null };
export type Claim = { text: string; status: "supported" | "partial" | "unsupported"; evidence: string[] };
export type Draft = { version: number; cover_letter: string; screening_answers?: Record<string, string>; claims?: Claim[] };
export type Risk = { client_score: number; flags: string[]; injection_spans: string[]; verdict: "ok" | "caution" | "block"; reasons: string[] };
export type Price = { amount: number; kind: "fixed" | "hourly"; band: [number, number]; connects_cost: number; worth_it: boolean; rationale: string };
export type Compliance = { allowed: boolean; violations: string[]; redactions: string[] };
export type ApprovalRequest = {
  kind: "proposal" | "message";
  thread_id: string;
  draft: Draft;
  risk?: Risk | null;
  price?: Price | null;
  claim_evidence: Record<string, string[]>;
  dry_run_preview: Record<string, unknown>;
  compliance?: Compliance | null;
};
export type TraceLine = { node: string; note?: string; ms?: number; tokens?: number };
export type RunState = {
  status?: string;
  attention_reason?: string;
  decision?: { action: "skip" | "watch" | "bid"; reasons: string[] };
  price?: Price;
  risk?: Risk;
  fit?: { score: number; matrix: Record<string, EvidenceRef[]>; gaps: string[]; reasons: string[] };
  draft?: Draft & { text?: string };
  critique?: { approve: boolean; issues: string[]; round: number };
  compliance?: Compliance;
  submission?: { proposal_id: string; status: string; connects_cost: number; idempotency_key: string; replayed: boolean };
  claims?: Claim[];
  intent?: { intent: string; confidence: number; injection_spans: string[] };
  job?: { job_id: string; title: string; description: string; skills?: string[] };
  trace?: TraceLine[];
  errors?: string[];
  approval_request?: ApprovalRequest | null;
  last_client_message?: string;
};
export type Run = {
  thread_id: string;
  kind: string;
  subject: string;
  title: string;
  status: string;
  stage?: string | null;
  tokens: number;
  steps: number;
  summary: RunState;
  created_at?: string | null;
};

/** evidence id -> snippet, collected from the Fit Matcher's evidence matrix. */
export function evidenceIndex(state?: RunState): Record<string, EvidenceRef> {
  const out: Record<string, EvidenceRef> = {};
  for (const refs of Object.values(state?.fit?.matrix ?? {})) for (const r of refs) out[r.evidence_id] = r;
  return out;
}
