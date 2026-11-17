"""Conversation graph - one thread per client conversation.

  new_message -> classify_intent -> (interview_request -> propose_slots) -> draft_reply
              -> message_compliance --(blocked)--> update_pipeline
              -> message_approval [interrupt()] -> send -> update_pipeline
Scam signals get a safe, on-platform reply drafted (still human-approved) and are flagged.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from agent.nodes.conversation import (
    classify_intent,
    draft_reply,
    message_approval,
    message_compliance,
    new_message,
    propose_slots,
    send,
    update_pipeline,
)
from agent.runtime import Deps
from agent.state import HALT, ConversationState


def _halted(s: dict) -> bool:
    return s.get("status") in HALT


def after_classify(s: dict) -> str:
    if _halted(s):
        return "update_pipeline"
    return "propose_slots" if s["intent"].intent == "interview_request" else "draft_reply"


def guard(nxt: str):
    return lambda s: "update_pipeline" if _halted(s) else nxt


def build_conversation_graph(config: dict, checkpointer=None, store=None):
    g = StateGraph(ConversationState, context_schema=Deps)
    for fn in (new_message, classify_intent, propose_slots, draft_reply, message_compliance, message_approval, send,
               update_pipeline):  # fmt: skip
        g.add_node(fn.node_name, fn)
    g.add_edge(START, "new_message")
    g.add_conditional_edges(
        "new_message", guard("classify_intent"), ["classify_intent", "update_pipeline"]
    )
    g.add_conditional_edges(
        "classify_intent", after_classify, ["propose_slots", "draft_reply", "update_pipeline"]
    )
    g.add_conditional_edges(
        "propose_slots", guard("draft_reply"), ["draft_reply", "update_pipeline"]
    )
    g.add_conditional_edges(
        "draft_reply", guard("message_compliance"), ["message_compliance", "update_pipeline"]
    )
    g.add_conditional_edges(
        "message_compliance", guard("message_approval"), ["message_approval", "update_pipeline"]
    )
    g.add_conditional_edges("message_approval", guard("send"), ["send", "update_pipeline"])
    g.add_edge("send", "update_pipeline")
    g.add_edge("update_pipeline", END)
    return g.compile(checkpointer=checkpointer, store=store)
