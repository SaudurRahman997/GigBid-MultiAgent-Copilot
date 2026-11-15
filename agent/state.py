"""Typed LangGraph state for the bid and conversation graphs.

Fields written by the parallel branches (job_analyst || risk_assessor || fit_matcher) or by
every node use reducers so concurrent updates merge instead of overwriting:
  steps    add      - step budget accounting (every node adds 1)
  tokens   add      - token budget accounting (LLM usage)
  trace    add      - per-node log lines (node, ms, note) for the run viewer
  errors   add      - failures recorded by any branch (dead-letter information)
Everything else has a single writer and uses last-write-wins.
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal, TypedDict

from agent.handoffs import (
    ApprovalDecision,
    BidDecision,
    ComplianceVerdict,
    Critique,
    FitReport,
    IntentResult,
    JobSpec,
    MessageDraft,
    PriceQuote,
    ProposalDraft,
    RiskReport,
    SubmissionResult,
)

Status = Literal["running", "skipped", "watch", "blocked", "awaiting_approval", "submitted", "sent",
                 "rejected", "needs_attention", "dead_letter", "done"]  # fmt: skip


class BidState(TypedDict, total=False):
    # input
    job_id: str
    thread_id: str
    user: str
    # parallel analysis (each branch writes its own key)
    job: dict
    profile: dict
    spec: JobSpec
    risk: RiskReport
    fit: FitReport
    # downstream
    decision: BidDecision
    price: PriceQuote
    evidence: list[dict]
    draft: ProposalDraft
    verify_report: dict
    critique: Critique
    critic_round: int
    compliance: ComplianceVerdict
    dry_run_preview: dict
    approval: ApprovalDecision
    submission: SubmissionResult
    status: Status
    attention_reason: str
    # reducers
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    trace: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]


class ConversationState(TypedDict, total=False):
    thread_id: str
    user: str
    messages: list[dict]
    last_client_message: str
    profile: dict
    intent: IntentResult
    evidence: list[dict]
    slots: list[dict]
    draft: MessageDraft
    compliance: ComplianceVerdict
    approval: ApprovalDecision
    sent_message_id: str
    pipeline_stage: str
    status: Status
    attention_reason: str
    steps: Annotated[int, operator.add]
    tokens: Annotated[int, operator.add]
    trace: Annotated[list[dict], operator.add]
    errors: Annotated[list[str], operator.add]


HALT = {"skipped", "watch", "blocked", "rejected", "needs_attention", "dead_letter"}
