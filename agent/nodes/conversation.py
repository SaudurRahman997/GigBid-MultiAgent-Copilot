"""Conversation graph nodes: new_message -> classify_intent -> draft_reply | propose_slots
-> message_compliance -> message_approval [interrupt] -> send -> update_pipeline."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from langgraph.types import interrupt

from agent.handoffs import (
    ApprovalDecision,
    ApprovalRequest,
    IntentResult,
    MessageDraft,
    ProposalDraft,
)
from agent.nodes.analysis import injection_spans
from agent.nodes.proposal import check_compliance
from agent.prompt_loader import render
from agent.runtime import Deps, ask, node, parse_json, untrusted

INTENT_RULES = [
    ("scam_signal", r"whats\s?app|telegram|deposit|outside the platform|bank transfer|your (email|number)|unpaid|sample project first"),
    ("interview_request", r"\b(call|interview|meeting|meet|video|zoom|available|availability|time slots?|schedule)\b"),
    ("negotiation", r"\b(price|budget|rate|discount|cheaper|lower|afford|\$\d+)\b"),
]  # fmt: skip
STAGE = {
    "question": "replied",
    "negotiation": "replied",
    "interview_request": "interview",
    "scam_signal": "flagged",
}


@node("new_message")
async def new_message(state: dict, deps: Deps) -> dict:
    res = await deps.mcp.call("liaison", "list_messages", {"thread_id": state["thread_id"]})
    msgs = res.get("messages") or []
    last = next((m["text"] for m in reversed(msgs) if m["sender"] == "client"), "")
    profile = await deps.mcp.call("liaison", "get_profile", {})
    return {"messages": msgs, "last_client_message": last, "profile": profile, "status": "running",
            "_note": f"{len(msgs)} messages"}  # fmt: skip


def rules_intent(text: str) -> IntentResult:
    for intent, pat in INTENT_RULES:
        if re.search(pat, text, re.I):
            return IntentResult(intent=intent, confidence=0.7)
    return IntentResult(intent="question", confidence=0.5)


@node("classify_intent")
async def classify_intent(state: dict, deps: Deps) -> dict:
    text = state["last_client_message"]
    spans = injection_spans(text, deps.policy["injection_patterns"])
    result = rules_intent(text)
    tokens = 0
    if deps.mode("classify_intent") == "llm":
        try:
            out_text, tokens = await ask(
                deps,
                "classify_intent",
                render("classify_intent", message=untrusted("CLIENT MESSAGE", text)),
            )
            out = parse_json(out_text)
            result = IntentResult(
                intent=out["intent"], confidence=float(out.get("confidence", 0.7))
            )
        except Exception:  # noqa: BLE001 - keep the rules result
            pass
    if result.intent != "scam_signal" and rules_intent(text).intent == "scam_signal":
        result = IntentResult(
            intent="scam_signal", confidence=max(result.confidence, 0.7)
        )  # safety override
    result.injection_spans = spans
    return {
        "intent": result,
        "tokens": tokens,
        "_note": f"{result.intent} ({result.confidence:.2f})",
    }


@node("propose_slots")
async def propose_slots(state: dict, deps: Deps) -> dict:
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0) + timedelta(days=1)
    res = await deps.mcp.call("liaison", "free_slots", {"start": start.isoformat(), "end": (start + timedelta(days=5)).isoformat(),
                                                        "duration_min": 30})  # fmt: skip
    return {"slots": res["slots"][:3], "_note": f"{len(res['slots'][:3])} slots"}


def human_time(iso: str) -> str:
    """'2026-11-03T10:00:00Z' -> 'Tue 03 Nov, 10:00 UTC' (no long digit runs that look like phone numbers)."""
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%a %d %b, %H:%M UTC")


def rules_reply(intent: str, slots: list[dict], profile: dict) -> str:
    if intent == "scam_signal":
        return ("Thanks for reaching out! To keep things safe for both of us I keep all communication and "
                "payments here on the platform, and I don't do unpaid work or pay fees. Happy to continue here.")  # fmt: skip
    if intent == "interview_request":
        times = ", ".join(human_time(s["start"]) for s in slots) or "any weekday afternoon"
        return f"Happy to talk! I can do {times}. Let me know which works and we'll use the platform's call feature."
    if intent == "negotiation":
        return ("Thanks for being upfront about the budget. I can't go below my usual minimum, but I can propose a "
                "smaller first milestone so you can see results before committing to the full scope.")  # fmt: skip
    return f"Good question - as {profile.get('headline', 'a freelancer').split(' — ')[0].lower()}, here is how I'd approach it: I'd start with a short scoping call on the platform, then deliver in small, testable steps."


@node("draft_reply")
async def draft_reply(state: dict, deps: Deps) -> dict:
    intent = state["intent"].intent
    profile = state["profile"]
    slots = state.get("slots") or []
    evidence = []
    if intent in ("question", "negotiation"):
        res = await deps.mcp.call(
            "liaison",
            "search_evidence",
            {"requirement": state["last_client_message"][:500], "k": 3},
        )
        evidence = res["items"]
    text, tokens = rules_reply(intent, slots, profile), 0
    if deps.mode("liaison") == "llm":
        try:
            convo = "\n".join(f"{m['sender']}: {m['text']}" for m in state["messages"][-6:])
            text, tokens = await ask(deps, "liaison", render(
                "liaison", intent=intent, floor=f"${profile['floors']['hourly']}/h or ${profile['floors']['fixed']} fixed",
                slots=", ".join(human_time(s["start"]) for s in slots) or "(none)", conversation=untrusted("CONVERSATION", convo),
                evidence="\n".join(f"- {e['id']}: {e['snippet']}" for e in evidence) or "(none)"))  # fmt: skip
        except Exception:  # noqa: BLE001 - keep the safe template
            text = rules_reply(intent, slots, profile)
    version = state["draft"].version + 1 if state.get("draft") else 1
    return {"draft": MessageDraft(version=version, text=text.strip(), proposed_slots=slots), "evidence": evidence,
            "tokens": tokens, "_note": f"reply v{version} ({intent})"}  # fmt: skip


@node("message_compliance")
async def message_compliance(state: dict, deps: Deps) -> dict:
    verdict = check_compliance(state["draft"].text, deps.policy, [])
    out: dict = {
        "compliance": verdict,
        "_note": "allowed" if verdict.allowed else f"blocked {verdict.violations}",
    }
    if not verdict.allowed:
        out |= {
            "status": "blocked",
            "attention_reason": f"compliance: {', '.join(verdict.violations)}",
        }
    return out


@node("message_approval")
async def message_approval(state: dict, deps: Deps) -> dict:
    d = state["draft"]
    req = ApprovalRequest(kind="message", thread_id=state["thread_id"], draft=ProposalDraft(version=d.version, cover_letter=d.text),
                          compliance=state.get("compliance"), dry_run_preview={"thread_id": state["thread_id"], "text": d.text,
                                                                               "proposed_slots": d.proposed_slots})  # fmt: skip
    decision = ApprovalDecision.model_validate(interrupt(req.model_dump(mode="json")))
    out: dict = {"approval": decision, "_note": decision.action}
    if decision.action == "reject":
        out |= {
            "status": "rejected",
            "attention_reason": f"rejected by human: {decision.reason or 'no reason'}",
        }
    elif decision.action == "edit" and decision.edited_text:
        out["draft"] = d.model_copy(
            update={"text": decision.edited_text.strip(), "version": d.version + 1}
        )
    return out


@node("send")
async def send(state: dict, deps: Deps) -> dict:
    d = state["draft"]
    verdict = check_compliance(d.text, deps.policy, [])  # edited text is re-checked before sending
    if not verdict.allowed:
        return {
            "compliance": verdict,
            "status": "blocked",
            "attention_reason": f"compliance after edit: {verdict.violations}",
        }
    key = f"{state['thread_id']}:msg:v{d.version}"
    res = await deps.mcp.call(
        "liaison",
        "send_message",
        {"thread_id": state["thread_id"], "text": d.text, "idempotency_key": key},
    )
    for i, slot in enumerate(d.proposed_slots):
        await deps.mcp.call("liaison", "create_tentative_hold", {"start": slot["start"], "duration_min": 30,
                                                                 "title": f"Client call ({state['thread_id']})",
                                                                 "idempotency_key": f"{key}:hold{i}"})  # fmt: skip
    return {
        "sent_message_id": res["message_id"],
        "status": "sent",
        "_note": f"sent {res['message_id']}",
    }


@node("update_pipeline")
async def update_pipeline(state: dict, deps: Deps) -> dict:
    status = state.get("status") or "done"
    stage = STAGE.get(state["intent"].intent, "replied") if state.get("intent") else "replied"
    return {"pipeline_stage": stage if status == "sent" else status, "status": "done" if status == "sent" else status,
            "_note": stage}  # fmt: skip
