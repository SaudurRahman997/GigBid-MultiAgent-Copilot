"""In-process stand-in for the MCP tool layer (graph tests + offline decision evals) (same tool names, same result shapes).

Backed by real Phase 1 data (dev-set jobs, clients, persona profiles, portfolio) with cheap
retrieval (BM25) and a token-overlap claim judge, so tests are fast and deterministic.
Write tools honour idempotency keys exactly like the real servers.
"""

from __future__ import annotations

import json
from pathlib import Path

from mcp_servers.marketplace.server import market_band
from rag.corpus import load_corpus
from rag.models import OverlapReranker
from rag.variants.bm25 import BM25Retriever
from rag.verify import RerankJudge, verify

ROOT = Path(__file__).resolve().parents[1]


class SimulatedCrash(BaseException):  # noqa: N818 - models a process dying (not an Exception: no retry)
    """The process dies mid-node (like SIGKILL); BaseException so no handler can swallow it."""
DATA = ROOT / "data"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").split("\n") if x]


class _RetrieverShim:
    """Gives verify() the .retrieve/.ctx interface over the BM25 baseline."""

    def __init__(self, persona: str):
        self.inner = BM25Retriever(load_corpus(persona))
        self.ctx = type("C", (), {"docs": load_corpus(persona)})()

    def retrieve(self, query, k=5, filters=None):
        return self.inner.search(query.sub_queries()[0], k, filters)


class FakeMCP:
    def __init__(self, persona: str = "ai_ml", connects: int = 500):
        self.persona = persona
        self.jobs = {j["job_id"]: j for p in ("ai_ml", "fullstack", "data_analyst") for j in _jsonl(DATA / "devset" / f"{p}.jsonl")}
        self.clients = {c["client_id"]: c for c in _jsonl(DATA / "synthetic" / "clients.jsonl")}
        self.profile = json.loads((DATA / "personas" / persona / "profile.json").read_text(encoding="utf-8"))
        self.retriever = BM25Retriever(load_corpus(persona))
        self.shim = _RetrieverShim(persona)
        self.balance = connects
        self.drafts: dict[str, dict] = {}
        self.idem: dict[tuple[str, str], dict] = {}
        self.calls: list[tuple[str, str]] = []
        self.submits = 0  # real submissions (not replays)
        self.lose_next_submit_response = False
        self.crash_after_submit = False
        self.threads = {"th_test": [{"id": "m1", "sender": "freelancer", "text": "Thanks for considering my proposal."},
                                    {"id": "m2", "sender": "client", "text": "Can we schedule a call this week?"}]}  # fmt: skip
        self.sent: list[dict] = []
        self.holds: list[dict] = []

    async def call(self, agent: str, tool: str, args: dict) -> dict:
        self.calls.append((agent, tool))
        return await getattr(self, f"t_{tool}")(args)

    # ------------------------------------------------------------------ reads
    async def t_search_jobs(self, a):
        q, cat = (a.get("query") or "").lower(), a.get("category")
        hits = [j for j in self.jobs.values() if (not cat or j.get("category") == cat)
                and (not q or q in f"{j['title']} {j['description']}".lower())]  # fmt: skip
        keep = ("job_id", "title", "category", "pay_type", "budget_usd", "hourly_low", "hourly_high", "client_id",
                "connects_required", "applicants", "posted_at", "skills")  # fmt: skip
        return {"items": [{k: j.get(k) for k in keep} for j in hits[: a.get("limit") or 20]], "total": len(hits)}

    async def t_get_job(self, a):
        j = self.jobs[a["job_id"]]
        return {k: v for k, v in j.items() if not k.startswith("_") and k != "requirements"}

    async def t_get_client_history(self, a):
        c = self.clients[a["client_id"]]
        return {k: v for k, v in c.items() if not k.startswith("_")}

    async def t_get_profile(self, a):
        return self.profile

    async def t_search_evidence(self, a):
        hits = self.retriever.search(a["requirement"], a.get("k", 5))
        return {"variant": "bm25_baseline", "items": [{"id": h.doc.id, "type": h.doc.type, "snippet": h.snippet, "score": h.score,
                                                       "outcome": h.doc.outcome} for h in hits]}  # fmt: skip

    async def t_get_market_rates(self, a):
        return market_band(DATA, a["category"], a.get("skills") or [], a["pay_type"]).model_dump()

    async def t_verify_claims(self, a):
        checks = verify(a["draft"], self.shim, RerankJudge(OverlapReranker(), 0.3, 0.15), k=3)
        return {"checks": [{"text": c.text, "status": c.status, "evidence": c.evidence, "cited": c.cited, "reason": c.reason}
                           for c in checks], "unsupported_rate": 0.0, "judge": "overlap"}  # fmt: skip

    async def t_get_connects_balance(self, a):
        return {"balance": self.balance}

    async def t_list_messages(self, a):
        return {"messages": self.threads[a["thread_id"]]} if a.get("thread_id") else {"threads": list(self.threads)}

    async def t_free_slots(self, a):
        return {"slots": [{"start": f"2026-11-0{d}T10:00:00Z", "end": f"2026-11-0{d}T10:30:00Z"} for d in (3, 4, 5, 6)]}

    # ------------------------------------------------------------------ writes (idempotent)
    def _replay(self, tool, key):
        hit = self.idem.get((tool, key))
        return {**hit, "replayed": True} if hit else None

    async def t_create_proposal_draft(self, a):
        job = self.jobs[a["job_id"]]
        cost = int(job.get("connects_required") or 8)
        if a.get("dry_run"):
            return {"dry_run": True, "proposal_id": None, "job_id": a["job_id"], "connects_cost": cost,
                    "would_send": {k: a[k] for k in ("job_id", "cover_letter", "bid_amount")}, "replayed": False}  # fmt: skip
        if r := self._replay("draft", a["idempotency_key"]):
            return r
        pid = f"pr_{len(self.drafts) + 1:06d}"
        self.drafts[pid] = {"job_id": a["job_id"], "cover_letter": a["cover_letter"], "cost": cost, "status": "draft"}
        res = {"dry_run": False, "proposal_id": pid, "job_id": a["job_id"], "connects_cost": cost, "replayed": False}
        self.idem[("draft", a["idempotency_key"])] = res
        return res

    async def t_submit_proposal(self, a):
        if r := self._replay("submit", a["idempotency_key"]):
            return r
        d = self.drafts[a["proposal_id"]]
        d["status"] = "submitted"
        self.balance -= d["cost"]
        self.submits += 1
        res = {"dry_run": False, "proposal_id": a["proposal_id"], "status": "submitted", "connects_cost": d["cost"],
               "balance_after": self.balance, "replayed": False}  # fmt: skip
        self.idem[("submit", a["idempotency_key"])] = res
        if self.crash_after_submit:
            self.crash_after_submit = False
            raise SimulatedCrash("process died right after the marketplace accepted the submit")
        if self.lose_next_submit_response:
            self.lose_next_submit_response = False
            raise ConnectionError("simulated lost response after the submit was processed")
        return res

    async def t_send_message(self, a):
        if r := self._replay("msg", a["idempotency_key"]):
            return r
        res = {"dry_run": False, "thread_id": a["thread_id"], "message_id": f"m{len(self.sent) + 10}", "replayed": False}
        self.sent.append({"text": a["text"], **res})
        self.idem[("msg", a["idempotency_key"])] = res
        return res

    async def t_create_tentative_hold(self, a):
        if r := self._replay("hold", a["idempotency_key"]):
            return r
        res = {"dry_run": False, "hold_id": f"hold_{len(self.holds)}", "start": a["start"], "replayed": False}
        self.holds.append(res)
        self.idem[("hold", a["idempotency_key"])] = res
        return res
