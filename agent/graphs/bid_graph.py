"""Bid graph - one thread per job (hand-written StateGraph, R3/R4).

  scout_in -> [job_analyst || risk_assessor || fit_matcher]  (Send fan-out, fan-in at decide)
           -> decide (skip | watch -> record_outcome | bid)
           -> pricing -> writer -> verify_claims -> critic --(issues, round < max)--> writer
                                                         \\-> compliance --(blocked)--> record_outcome
           -> prepare_approval -> approval [interrupt()]
                -> approve -> submit -> record_outcome
                -> edit    -> apply_edit -> compliance_recheck -> submit | prepare_approval
                -> reject  -> record_outcome
Any node that hits a budget, a degraded marketplace or an unrecoverable error sets a halting
status (needs_attention / dead_letter) and every router then goes straight to record_outcome.
Nothing reaches `submit` without passing the approval interrupt.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from agent.nodes.analysis import fit_matcher, job_analyst, risk_assessor, scout_in
from agent.nodes.approval import apply_edit, approval, prepare_approval, record_outcome, submit
from agent.nodes.proposal import compliance, critic, decide, pricing, verify_claims, writer
from agent.runtime import Deps, node
from agent.state import HALT, BidState

ANALYSTS = ("job_analyst", "risk_assessor", "fit_matcher")
compliance_recheck = node("compliance_recheck")(compliance.inner)


def halted(state: dict) -> bool:
    return state.get("status") in HALT


def after_scout(state: dict):
    if halted(state):
        return "record_outcome"
    return [Send(name, state) for name in ANALYSTS]


def after_decide(state: dict) -> str:
    if halted(state) or state["decision"].action != "bid":
        return "record_outcome"
    return "pricing"


def after_critic(state: dict, max_rounds: int) -> str:
    if halted(state):
        return "record_outcome"
    c = state["critique"]
    return "compliance" if c.approve or state.get("critic_round", 0) >= max_rounds else "writer"


def after_compliance(state: dict) -> str:
    return "record_outcome" if halted(state) else "prepare_approval"


def after_approval(state: dict) -> str:
    if halted(state):
        return "record_outcome"
    return {"approve": "submit", "edit": "apply_edit"}.get(
        state["approval"].action, "record_outcome"
    )


def after_recheck(state: dict) -> str:
    if state.get("compliance") and state["compliance"].allowed:
        return "submit"
    return "prepare_approval"  # edited text broke a rule: back to the human with the violations


def guard(next_node: str):
    return lambda s: "record_outcome" if halted(s) else next_node


async def _decide_guarded(state: dict, runtime):
    missing = [k for k in ("spec", "risk", "fit", "profile") if k not in state]
    if missing or halted(state):
        return {"status": state.get("status") if halted(state) else "needs_attention",
                "attention_reason": state.get("attention_reason") or f"analysis incomplete: missing {missing}"}  # fmt: skip
    return await decide(state, runtime)


def build_bid_graph(config: dict, checkpointer=None, store=None):
    max_rounds = int(config["loops"]["critic_max_rounds"])
    g = StateGraph(BidState, context_schema=Deps)
    for fn in (scout_in, job_analyst, risk_assessor, fit_matcher, pricing, writer, verify_claims, critic,
               compliance, compliance_recheck, prepare_approval, approval, apply_edit, submit, record_outcome):  # fmt: skip
        g.add_node(fn.node_name, fn)
    g.add_node("decide", _decide_guarded)

    g.add_edge(START, "scout_in")
    g.add_conditional_edges("scout_in", after_scout, [*ANALYSTS, "record_outcome"])
    for name in ANALYSTS:
        g.add_edge(name, "decide")  # fan-in: decide runs once all three branches finished
    g.add_conditional_edges("decide", after_decide, ["pricing", "record_outcome"])
    g.add_conditional_edges("pricing", guard("writer"), ["writer", "record_outcome"])
    g.add_conditional_edges("writer", guard("verify_claims"), ["verify_claims", "record_outcome"])
    g.add_conditional_edges("verify_claims", guard("critic"), ["critic", "record_outcome"])
    g.add_conditional_edges(
        "critic", lambda s: after_critic(s, max_rounds), ["writer", "compliance", "record_outcome"]
    )
    g.add_conditional_edges("compliance", after_compliance, ["prepare_approval", "record_outcome"])
    g.add_conditional_edges("prepare_approval", guard("approval"), ["approval", "record_outcome"])
    g.add_conditional_edges("approval", after_approval, ["submit", "apply_edit", "record_outcome"])
    g.add_conditional_edges(
        "apply_edit", guard("compliance_recheck"), ["compliance_recheck", "record_outcome"]
    )
    g.add_conditional_edges("compliance_recheck", after_recheck, ["submit", "prepare_approval"])
    g.add_conditional_edges("submit", guard("record_outcome"), ["record_outcome"])
    g.add_edge("record_outcome", END)
    return g.compile(checkpointer=checkpointer, store=store)
