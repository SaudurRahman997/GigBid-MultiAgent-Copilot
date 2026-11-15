"""Structured hand-offs between agents (BUILD_SPEC Appendix C). Every node reads and writes these
Pydantic models, never free text, so each step can be validated, logged and replayed."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskFlag = Literal["free_work", "off_platform", "upfront_fee", "injection", "vague_high_budget", "duplicate"]
Intent = Literal["question", "negotiation", "interview_request", "scam_signal"]


class Requirement(BaseModel):
    text: str
    kind: Literal["skill", "deliverable", "constraint"] = "skill"
    must_have: bool = False
    skill: str | None = Field(None, description="Canonical skill name when the requirement is a skill")


class Budget(BaseModel):
    pay_type: Literal["fixed", "hourly"]
    amount: float | None = None
    hourly_low: float | None = None
    hourly_high: float | None = None


class JobSpec(BaseModel):
    job_id: str
    title: str
    requirements: list[Requirement]
    budget: Budget
    timeline: str | None = None
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list)
    category: str = "other"
    client_id: str | None = None
    connects_required: int | None = None
    applicants: str | None = None


class RiskReport(BaseModel):
    client_score: float = Field(ge=0, le=1)
    flags: list[RiskFlag] = Field(default_factory=list)
    injection_spans: list[str] = Field(default_factory=list)
    verdict: Literal["ok", "caution", "block"] = "ok"
    reasons: list[str] = Field(default_factory=list)


class EvidenceRef(BaseModel):
    evidence_id: str
    snippet: str
    score: float
    outcome: str | None = None


class FitReport(BaseModel):
    score: float = Field(ge=0, le=1)
    matrix: dict[str, list[EvidenceRef]] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class BidDecision(BaseModel):
    action: Literal["skip", "watch", "bid"]
    reasons: list[str] = Field(default_factory=list)
    auto: bool = Field(False, description="True if taken by the autonomy setting without a human")


class PriceQuote(BaseModel):
    amount: float
    kind: Literal["fixed", "hourly"]
    band: tuple[float, float]
    connects_cost: int
    worth_it: bool
    rationale: str


class Claim(BaseModel):
    text: str
    status: Literal["supported", "partial", "unsupported"]
    evidence: list[str] = Field(default_factory=list)


class ProposalDraft(BaseModel):
    version: int = 1
    cover_letter: str
    screening_answers: dict[str, str] = Field(default_factory=dict)
    claims: list[Claim] = Field(default_factory=list)


class Critique(BaseModel):
    approve: bool
    issues: list[str] = Field(default_factory=list)
    round: int = 1


class ComplianceVerdict(BaseModel):
    allowed: bool
    violations: list[str] = Field(default_factory=list)
    redactions: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    kind: Literal["proposal", "message"] = "proposal"
    thread_id: str
    draft: ProposalDraft
    risk: RiskReport | None = None
    price: PriceQuote | None = None
    claim_evidence: dict[str, list[str]] = Field(default_factory=dict, description="claim -> evidence ids")
    dry_run_preview: dict = Field(default_factory=dict)
    compliance: ComplianceVerdict | None = None


class ApprovalDecision(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = None
    reason: str | None = None


class SubmissionResult(BaseModel):
    proposal_id: str
    status: str
    connects_cost: int
    idempotency_key: str
    replayed: bool = False


class IntentResult(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0, le=1)
    injection_spans: list[str] = Field(default_factory=list)


class MessageDraft(BaseModel):
    version: int = 1
    text: str
    proposed_slots: list[dict] = Field(default_factory=list)
