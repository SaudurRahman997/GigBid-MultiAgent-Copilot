"""Human approval and submission.

prepare_approval  dry-run preview of the exact payload and Connects cost (read-only, idempotent)
approval          interrupt(ApprovalRequest) - the graph pauses until a human resumes it with
                  Command(resume=ApprovalDecision); a node re-runs from its start on resume, so
                  it does nothing before interrupt() except read state
apply_edit        human edited the text: new draft version, diff kept for style memory,
                  then Compliance re-checks it before anything is sent
submit            draft + submit through MCP with idempotency keys derived from
                  (thread id, draft version): a crash after approval and a resume re-runs this
                  node, and the servers replay the stored results -> exactly one submission
record_outcome    final status for the run viewer / pipeline
"""

from __future__ import annotations

import difflib

from langgraph.types import interrupt

from agent.handoffs import ApprovalDecision, ApprovalRequest, SubmissionResult
from agent.memory.store import record_edit
from agent.runtime import Deps, node


def keys(thread_id: str, version: int) -> tuple[str, str]:
    return f"{thread_id}:draft:v{version}", f"{thread_id}:submit:v{version}"


@node("prepare_approval")
async def prepare_approval(state: dict, deps: Deps) -> dict:
    draft, price = state["draft"], state["price"]
    draft_key, _ = keys(state["thread_id"], draft.version)
    preview = await deps.mcp.call("submitter_preview", "create_proposal_draft", {
        "job_id": state["job_id"], "cover_letter": draft.cover_letter.ljust(50), "bid_amount": float(price.amount),
        "screening_answers": draft.screening_answers or None, "idempotency_key": draft_key, "dry_run": True,
    })  # fmt: skip
    balance = await deps.mcp.call("submitter_preview", "get_connects_balance", {})
    preview["connects_balance"] = balance["balance"]
    return {"dry_run_preview": preview, "status": "awaiting_approval", "_note": f"cost {preview['connects_cost']}"}


@node("approval")
async def approval(state: dict, deps: Deps) -> dict:
    draft = state["draft"]
    request = ApprovalRequest(
        kind="proposal", thread_id=state["thread_id"], draft=draft, risk=state.get("risk"), price=state.get("price"),
        claim_evidence={c.text: c.evidence for c in draft.claims}, dry_run_preview=state.get("dry_run_preview", {}),
        compliance=state.get("compliance"),
    )  # fmt: skip
    raw = interrupt(request.model_dump(mode="json"))
    decision = ApprovalDecision.model_validate(raw)
    status = {"approve": "running", "edit": "running", "reject": "rejected"}[decision.action]
    out: dict = {"approval": decision, "status": status, "_note": decision.action}
    if decision.action == "reject":
        out["attention_reason"] = f"rejected by human: {decision.reason or 'no reason given'}"
    return out


@node("apply_edit")
async def apply_edit(state: dict, deps: Deps) -> dict:
    old, decision = state["draft"], state["approval"]
    new_text = (decision.edited_text or old.cover_letter).strip()
    diff = list(difflib.unified_diff(old.cover_letter.split(), new_text.split(), lineterm="", n=0))
    record_edit(deps.store, deps.user, state["thread_id"], old.cover_letter, new_text)
    new = old.model_copy(update={"cover_letter": new_text, "version": old.version + 1})
    return {"draft": new, "_note": f"edited -> v{new.version} ({len(diff)} diff lines)"}


@node("submit")
async def submit(state: dict, deps: Deps) -> dict:
    draft, price = state["draft"], state["price"]
    draft_key, submit_key = keys(state["thread_id"], draft.version)
    d = await deps.mcp.call("submitter", "create_proposal_draft", {
        "job_id": state["job_id"], "cover_letter": draft.cover_letter.ljust(50), "bid_amount": float(price.amount),
        "screening_answers": draft.screening_answers or None, "idempotency_key": draft_key,
    })  # fmt: skip
    r = await deps.mcp.call("submitter", "submit_proposal", {"proposal_id": d["proposal_id"], "idempotency_key": submit_key})
    sub = SubmissionResult(proposal_id=r["proposal_id"], status=r["status"], connects_cost=r["connects_cost"],
                           idempotency_key=submit_key, replayed=bool(r.get("replayed")))  # fmt: skip
    return {"submission": sub, "status": "submitted", "_note": f"{sub.proposal_id} replayed={sub.replayed}"}


@node("record_outcome")
async def record_outcome(state: dict, deps: Deps) -> dict:
    status = state.get("status") or "done"
    if status == "running":
        status = "done"
    return {"status": status, "_note": status}


__all__ = ["ApprovalDecision"]
