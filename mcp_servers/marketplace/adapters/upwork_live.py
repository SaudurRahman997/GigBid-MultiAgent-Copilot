"""Live Upwork adapter (stub until Phase 10).

Phase 10 connects to Upwork's official MCP server (https://mcp.upwork.com/mcp, Streamable HTTP,
OAuth 2.1 per user) through MultiServerMCPClient and maps its tools onto this port. Rules that
will hold then and hold now:
  * writes only create DRAFTS after GigBid approval; the user confirms on Upwork;
  * no browser automation, no cookies, no scraping;
  * reads run on a conservative schedule (docs/RUNBOOK.md).
Until then every operation raises, so selecting `marketplace: upwork_live` fails loudly instead
of silently pretending to work. Each port method is spelled out so the class visibly satisfies
the MarketplacePort protocol.
"""

from __future__ import annotations

from agent.marketplace_port import (
    ClientHistory,
    ConnectsBalance,
    DraftResult,
    Job,
    JobPage,
    MarketplaceError,
    Message,
    Policy,
    SentMessage,
    SubmitResult,
    Thread,
)


def _not_ready(operation: str) -> MarketplaceError:
    return MarketplaceError(
        f"upwork_live adapter: '{operation}' is not implemented yet (Phase 10). "
        "Set `marketplace: gigsim` in agent/config.yaml.",
        status=501,
    )


class UpworkLiveAdapter:
    name = "upwork_live"

    def __init__(self, *args, **kwargs):
        self._args = (args, kwargs)

    async def search_jobs(self, user, query, category, since, limit) -> JobPage:
        raise _not_ready("search_jobs")

    async def get_job(self, user, job_id) -> Job:
        raise _not_ready("get_job")

    async def get_client_history(self, user, client_id) -> ClientHistory:
        raise _not_ready("get_client_history")

    async def get_connects_balance(self, user) -> ConnectsBalance:
        raise _not_ready("get_connects_balance")

    async def list_threads(self, user) -> list[Thread]:
        raise _not_ready("list_threads")

    async def list_messages(self, user, thread_id) -> list[Message]:
        raise _not_ready("list_messages")

    async def get_policy(self, user) -> Policy:
        raise _not_ready("get_policy")

    async def create_proposal_draft(
        self, user, job_id, cover_letter, bid_amount, screening_answers
    ) -> DraftResult:
        raise _not_ready("create_proposal_draft")

    async def get_proposal(self, user, proposal_id) -> DraftResult:
        raise _not_ready("get_proposal")

    async def submit_proposal(self, user, proposal_id, idempotency_key) -> SubmitResult:
        raise _not_ready("submit_proposal")

    async def send_message(self, user, thread_id, text) -> SentMessage:
        raise _not_ready("send_message")

    async def health(self) -> bool:
        return False
