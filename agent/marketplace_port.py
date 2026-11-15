"""The one marketplace port (R1). Adapters implement it; nothing above it knows which one runs.

    agent graph -> MCP tools (mcp_servers/marketplace) -> MarketplacePort -> adapter
                                                           ├─ adapters/gigsim.py      (dev, grading)
                                                           └─ adapters/upwork_live.py (real use)

The adapter is chosen by `marketplace:` in agent/config.yaml. Models here are the canonical,
marketplace-neutral shapes every adapter must map into.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Protocol, runtime_checkable

import yaml
from pydantic import BaseModel, Field

CONFIG = Path(__file__).with_name("config.yaml")


class MarketplaceError(Exception):
    """Base error; `code` is stable so tools and agents can branch on it."""

    code = "marketplace_error"

    def __init__(self, message: str, *, status: int | None = None, detail: object = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


class MarketplaceUnavailable(MarketplaceError):
    code = "marketplace_unavailable"  # degraded mode: retries exhausted / connection refused


class RateLimited(MarketplaceError):
    code = "rate_limited"


class NotFound(MarketplaceError):
    code = "not_found"


class PolicyViolation(MarketplaceError):
    code = "policy_violation"


class InsufficientConnects(MarketplaceError):
    code = "insufficient_connects"


class Conflict(MarketplaceError):
    code = "conflict"


# ----------------------------------------------------------------------------- canonical models


class JobSummary(BaseModel):
    job_id: str
    title: str
    category: str | None = None
    skills: list[str] = Field(default_factory=list)
    pay_type: Literal["fixed", "hourly"] | str
    budget_usd: float | None = None
    hourly_low: float | None = None
    hourly_high: float | None = None
    client_id: str
    connects_required: int | None = None
    applicants: str | None = None
    posted_at: str | None = None


class Job(JobSummary):
    description: str
    experience_level: str | None = None
    screening_questions: list[str] = Field(default_factory=list)


class JobPage(BaseModel):
    total: int
    items: list[JobSummary]


class ClientHistory(BaseModel):
    client_id: str
    country: str | None = None
    payment_verified: bool | None = None
    total_spent_usd: float | None = None
    rating: float | None = None
    feedback_count: int | None = None
    hires: int | None = None
    jobs_posted: int | None = None
    hire_rate: float | None = None
    member_since: str | None = None
    avg_hourly_rate_paid_usd: float | None = None


class ConnectsBalance(BaseModel):
    balance: int


class Thread(BaseModel):
    thread_id: str
    client_id: str
    job_id: str | None = None
    last_message: str | None = None


class Message(BaseModel):
    message_id: str
    sender: Literal["freelancer", "client"] | str
    text: str
    ts: str | None = None


class Policy(BaseModel):
    version: str
    connects_multiplier_if_applicants_over_20: int = 1
    max_connects_per_proposal: int = 16
    external_links_allowed: bool = True
    max_cover_letter_chars: int = 5000


class DraftResult(BaseModel):
    proposal_id: str
    job_id: str
    status: str
    connects_cost: int


class SubmitResult(BaseModel):
    proposal_id: str
    status: str
    connects_cost: int
    balance_after: int | None = None
    replayed: bool = False


class SentMessage(BaseModel):
    message_id: str
    thread_id: str
    ts: str | None = None


# ----------------------------------------------------------------------------- the port


@runtime_checkable
class MarketplacePort(Protocol):
    name: str

    async def search_jobs(
        self, user: str, query: str | None, category: str | None, since: str | None, limit: int
    ) -> JobPage: ...
    async def get_job(self, user: str, job_id: str) -> Job: ...
    async def get_client_history(self, user: str, client_id: str) -> ClientHistory: ...
    async def get_connects_balance(self, user: str) -> ConnectsBalance: ...
    async def list_threads(self, user: str) -> list[Thread]: ...
    async def list_messages(self, user: str, thread_id: str) -> list[Message]: ...
    async def get_policy(self, user: str) -> Policy: ...
    async def create_proposal_draft(
        self,
        user: str,
        job_id: str,
        cover_letter: str,
        bid_amount: float,
        screening_answers: dict[str, str],
    ) -> DraftResult: ...
    async def get_proposal(self, user: str, proposal_id: str) -> DraftResult: ...
    async def submit_proposal(
        self, user: str, proposal_id: str, idempotency_key: str
    ) -> SubmitResult: ...
    async def send_message(self, user: str, thread_id: str, text: str) -> SentMessage: ...
    async def health(self) -> bool: ...


def load_config(path: Path = CONFIG) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def get_marketplace(config: dict | None = None, **kwargs) -> MarketplacePort:
    """Adapter selected by config (`marketplace: gigsim | upwork_live`)."""
    name = (config or load_config()).get("marketplace", "gigsim")
    if name == "gigsim":
        from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter

        return GigSimAdapter(**kwargs)
    if name == "upwork_live":
        from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter

        return UpworkLiveAdapter(**kwargs)
    raise ValueError(f"unknown marketplace adapter {name!r}")
