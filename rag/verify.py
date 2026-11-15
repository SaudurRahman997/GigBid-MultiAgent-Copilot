"""Claim verification (R5): split a draft into atomic claims, check each against portfolio
evidence, remove (or flag for rewrite) unsupported claims before the Critic sees the draft.

    checks = verify(draft, retriever, judge)        -> list[ClaimCheck]
    cleaned, report = repair(draft, checks)         -> draft without unsupported claims
    unsupported_rate(checks)                        -> share of claims unsupported

Judges
  RerankJudge  deterministic: cross-encoder logit of (claim, evidence) against calibrated
               thresholds, plus a strict number check (every number in the claim must appear in
               the supporting evidence, else at most "partial"). Default; free; reproducible.
  LLMJudge     the `verifier` model with agent/prompts/claim_judge.v1.md (JSON output).
Thresholds live in agent/config.yaml `verify:`; judge agreement with human labels (Cohen's
kappa) is measured by evals/runners/judge_calibration.py.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Literal, Protocol

import yaml

from rag.query import RetrievalQuery

ROOT = Path(__file__).resolve().parents[1]
Status = Literal["supported", "partial", "unsupported"]
CITE = re.compile(r"\s*\[([a-z_]+:[a-z_]+:[A-Za-z0-9_\-]+|[a-z_]+:cv)\]")
SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")
NUMBER = re.compile(r"\d+(?:[.,]\d+)?\s?%?")
# Sentences that make a checkable statement about the freelancer's past or abilities.
CLAIM_CUES = re.compile(
    r"\b(i|we|my|our)\b.*\b(built|build|created|delivered|developed|designed|cut|reduced|raised|"
    r"increased|lifted|saved|improved|grew|automated|trained|deployed|led|shipped|worked|"
    r"migrated|analy[sz]ed|implemented|experience|years|clients?|projects?|specialis[ez]|expert)\b"
    r"|\d+\s?%|\b\d{2,}\b",
    re.I,
)
NON_CLAIM = re.compile(
    r"^(happy to|i can start|let me know|looking forward|i would|i'd|i will|i'll|could we|"
    r"shall we|thanks|thank you|hi\b|hello|dear)",
    re.I,
)


@dataclass
class ClaimCheck:
    text: str
    status: Status
    evidence: list[str] = field(default_factory=list)
    cited: list[str] = field(default_factory=list)
    reason: str = ""
    score: float | None = None


def config() -> dict:
    return yaml.safe_load((ROOT / "agent" / "config.yaml").read_text(encoding="utf-8"))["verify"]


def split_claims(draft: str) -> list[tuple[str, list[str]]]:
    """Atomic, checkable claims with the evidence ids they cite: [(claim, [ids]), ...]."""
    out = []
    for para in re.split(r"\n\s*\n|\n", draft):
        for sent in SENT.split(para.strip()):
            cited = CITE.findall(sent)
            clean = CITE.sub("", sent).strip()
            if len(clean.split()) < 4 or NON_CLAIM.match(clean) or clean.endswith("?"):
                continue
            if CLAIM_CUES.search(clean):
                out.append((clean, cited))
    return out


def numbers(text: str) -> set[str]:
    return {n.replace(",", "").replace(" ", "") for n in NUMBER.findall(text)}


class Judge(Protocol):
    name: str

    def judge(self, claim: str, evidence: list[tuple[str, str]]) -> ClaimCheck: ...


class RerankJudge:
    name = "rerank"

    def __init__(
        self, reranker, support_logit: float, partial_logit: float, numbers_must_match: bool = True
    ):
        self.reranker = reranker
        self.hi, self.lo = support_logit, partial_logit
        self.strict_numbers = numbers_must_match

    def judge(self, claim: str, evidence: list[tuple[str, str]]) -> ClaimCheck:
        if not evidence:
            return ClaimCheck(claim, "unsupported", reason="no evidence retrieved")
        scores = self.reranker.score(claim, [text for _, text in evidence])
        ranked = sorted(zip(evidence, scores, strict=True), key=lambda x: -x[1])
        (best_id, best_text), best = ranked[0]
        status: Status = (
            "supported" if best >= self.hi else "partial" if best >= self.lo else "unsupported"
        )
        reason = f"best evidence {best_id} scored {best:.2f}"
        if self.strict_numbers and status == "supported":
            missing = numbers(claim) - set().union(
                *(numbers(t) for (_, t), s in ranked if s >= self.lo)
            )
            if missing:
                status = "partial"
                reason += f"; numbers not in evidence: {sorted(missing)}"
        support = (
            [eid for (eid, _), s in ranked if s >= self.lo][:3] if status != "unsupported" else []
        )
        return ClaimCheck(claim, status, support, reason=reason, score=round(float(best), 3))


class LLMJudge:
    name = "llm"

    def __init__(self, model, max_evidence_chars: int = 600):
        self.model = model
        self.max_chars = max_evidence_chars

    def judge(self, claim: str, evidence: list[tuple[str, str]]) -> ClaimCheck:
        from agent.prompt_loader import render

        if not evidence:
            return ClaimCheck(claim, "unsupported", reason="no evidence retrieved")
        ev = "\n".join(f"- {eid}: {text[: self.max_chars]}" for eid, text in evidence)
        raw = self.model.invoke(render("claim_judge", claim=claim, evidence=ev)).content
        raw = re.sub(r"<think>.*?</think>", "", str(raw), flags=re.S)
        m = re.search(r"\{.*\}", raw, flags=re.S)
        try:
            out = json.loads(m.group(0)) if m else {}
        except json.JSONDecodeError:
            out = {}
        status = (
            out.get("status")
            if out.get("status") in ("supported", "partial", "unsupported")
            else "unsupported"
        )
        known = {eid for eid, _ in evidence}
        return ClaimCheck(
            claim,
            status,
            [e for e in out.get("evidence_ids", []) if e in known],
            reason=str(out.get("reason", "unparseable judge output"))[:300],
        )


def gather_evidence(claim: str, cited: list[str], retriever, k: int) -> list[tuple[str, str]]:
    """Evidence for a claim: the items it cites first, then the top retrieved items."""
    docs = {d.id: d for d in retriever.ctx.docs} if hasattr(retriever, "ctx") else {}
    out: dict[str, str] = {c: docs[c].text for c in cited if c in docs}
    for h in retriever.retrieve(RetrievalQuery.single(claim), k=k):
        out.setdefault(h.doc.id, h.doc.text if len(h.doc.text) < 1500 else h.snippet)
    return list(out.items())


def verify(draft: str, retriever, judge: Judge, k: int | None = None) -> list[ClaimCheck]:
    k = k or config()["k"]
    checks = []
    for claim, cited in split_claims(draft):
        check = judge.judge(claim, gather_evidence(claim, cited, retriever, k))
        check.cited = cited
        checks.append(check)
    return checks


def unsupported_rate(checks: list[ClaimCheck]) -> float:
    return sum(c.status == "unsupported" for c in checks) / len(checks) if checks else 0.0


def repair(draft: str, checks: list[ClaimCheck]) -> tuple[str, dict]:
    """Remove sentences holding unsupported claims; keep supported/partial (partial is flagged
    for the Writer to soften). Returns the cleaned draft and a before/after report."""
    bad = [c.text for c in checks if c.status == "unsupported"]
    kept = []
    for para in draft.split("\n"):
        sents = SENT.split(para)
        kept.append(" ".join(s for s in sents if CITE.sub("", s).strip() not in bad).strip())
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    after = [c for c in checks if c.status != "unsupported"]
    return cleaned, {
        "claims_before": len(checks),
        "unsupported_before": len(bad),
        "unsupported_rate_before": round(unsupported_rate(checks), 4),
        "claims_after": len(after),
        "unsupported_rate_after": round(unsupported_rate(after), 4),
        "partial_flagged": [c.text for c in checks if c.status == "partial"],
        "checks": [asdict(c) for c in checks],
    }


def default_judge(kind: str | None = None) -> Judge:
    cfg = config()
    kind = kind or cfg["judge"]
    if kind == "llm":
        from agent.llm import chat_model_for_node

        return LLMJudge(chat_model_for_node("verifier"))
    from rag.models import default_reranker

    return RerankJudge(
        default_reranker(), cfg["support_logit"], cfg["partial_logit"], cfg["numbers_must_match"]
    )
