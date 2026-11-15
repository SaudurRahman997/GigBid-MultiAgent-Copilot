"""GigSim adapter for the marketplace port.

Retries: 429 -> wait Retry-After (capped); 5xx / connection errors -> exponential backoff.
Every retry of submit reuses the SAME Idempotency-Key, so a lost response can never cause a
second submission or Connects charge. After the last retry -> MarketplaceUnavailable
(degraded mode upstream).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

import httpx

from agent.marketplace_port import (
    ClientHistory,
    Conflict,
    ConnectsBalance,
    DraftResult,
    InsufficientConnects,
    Job,
    JobPage,
    JobSummary,
    MarketplaceError,
    MarketplaceUnavailable,
    Message,
    NotFound,
    Policy,
    PolicyViolation,
    RateLimited,
    SentMessage,
    SubmitResult,
    Thread,
)
from mcp_servers.common.settings import MCPSettings

MAX_RETRY_AFTER_S = 10.0


class GigSimAdapter:
    name = "gigsim"

    def __init__(
        self,
        settings: MCPSettings | None = None,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
        backoff_base_s: float = 0.25,
        sleep=asyncio.sleep,
    ):
        self.s = settings or MCPSettings()
        self._factory = client_factory or (
            lambda: httpx.AsyncClient(base_url=self.s.gigsim_url, timeout=self.s.gigsim_timeout_s)
        )
        self.backoff = backoff_base_s
        self.sleep = sleep

    def _headers(self, user: str, extra: dict | None = None) -> dict:
        token = self.s.gigsim_token_for_user.get(user)
        if not token:
            raise MarketplaceError(f"no GigSim account for user {user!r}", status=403)
        return {"Authorization": f"Bearer {token}", **(extra or {})}

    async def _request(
        self,
        method: str,
        path: str,
        user: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        headers: dict | None = None,
    ) -> httpx.Response:
        last: Exception | None = None
        for attempt in range(self.s.gigsim_max_retries + 1):
            try:
                async with self._factory() as client:
                    resp = await client.request(
                        method, path, json=json, params=params, headers=self._headers(user, headers)
                    )
            except httpx.TransportError as exc:
                last = MarketplaceUnavailable(f"GigSim unreachable: {type(exc).__name__}")
                await self.sleep(self.backoff * 2**attempt)
                continue
            if resp.status_code == 429:
                wait = min(float(resp.headers.get("Retry-After", "1")), MAX_RETRY_AFTER_S)
                last = RateLimited(f"GigSim rate limit; retry after {wait}s", status=429)
                await self.sleep(wait)
                continue
            if resp.status_code >= 500:
                last = MarketplaceUnavailable(f"GigSim {resp.status_code}", status=resp.status_code)
                await self.sleep(self.backoff * 2**attempt)
                continue
            if resp.status_code >= 400:
                raise _map_error(resp)
            return resp
        assert last is not None
        raise last

    # ------------------------------------------------------------------ reads
    async def search_jobs(self, user, query, category, since, limit) -> JobPage:
        params = {
            k: v
            for k, v in {
                "query": query,
                "category": category,
                "since": since,
                "limit": limit,
            }.items()
            if v is not None
        }
        data = (await self._request("GET", "/jobs", user, params=params)).json()
        return JobPage(
            total=data["total"], items=[JobSummary.model_validate(j) for j in data["items"]]
        )

    async def get_job(self, user, job_id) -> Job:
        return Job.model_validate((await self._request("GET", f"/jobs/{job_id}", user)).json())

    async def get_client_history(self, user, client_id) -> ClientHistory:
        data = (await self._request("GET", f"/clients/{client_id}/history", user)).json()
        return ClientHistory.model_validate(data)

    async def get_connects_balance(self, user) -> ConnectsBalance:
        data = (await self._request("GET", "/me/connects", user)).json()
        return ConnectsBalance(balance=data["balance"])

    async def list_threads(self, user) -> list[Thread]:
        data = (await self._request("GET", "/threads", user)).json()
        return [
            Thread(
                thread_id=t["thread_id"],
                client_id=t["client_id"],
                job_id=t.get("job_id"),
                last_message=(t.get("last_message") or {}).get("text"),
            )
            for t in data["items"]
        ]

    async def list_messages(self, user, thread_id) -> list[Message]:
        data = (await self._request("GET", f"/threads/{thread_id}/messages", user)).json()
        return [
            Message(message_id=m["id"], sender=m["sender"], text=m["text"], ts=m.get("ts"))
            for m in data["items"]
        ]

    async def get_policy(self, user) -> Policy:
        p = (await self._request("GET", "/policy", user)).json()
        return Policy(
            version=p["version"],
            connects_multiplier_if_applicants_over_20=p["connects"][
                "multiplier_if_applicants_over_20"
            ],
            max_connects_per_proposal=p["connects"]["max_per_proposal"],
            external_links_allowed=p["proposals"]["external_links_allowed"],
            max_cover_letter_chars=p["proposals"]["max_cover_letter_chars"],
        )

    async def get_proposal(self, user, proposal_id) -> DraftResult:
        p = (await self._request("GET", f"/proposals/{proposal_id}", user)).json()
        return DraftResult(
            proposal_id=p["proposal_id"],
            job_id=p["job_id"],
            status=p["status"],
            connects_cost=p["connects_cost"],
        )

    # ------------------------------------------------------------------ writes
    async def create_proposal_draft(
        self, user, job_id, cover_letter, bid_amount, screening_answers
    ) -> DraftResult:
        body = {
            "job_id": job_id,
            "cover_letter": cover_letter,
            "bid_amount": bid_amount,
            "screening_answers": screening_answers,
        }
        p = (await self._request("POST", "/proposals", user, json=body)).json()
        return DraftResult(
            proposal_id=p["proposal_id"],
            job_id=p["job_id"],
            status=p["status"],
            connects_cost=p["connects_cost"],
        )

    async def submit_proposal(self, user, proposal_id, idempotency_key) -> SubmitResult:
        resp = await self._request(
            "POST",
            f"/proposals/{proposal_id}/submit",
            user,
            headers={"Idempotency-Key": idempotency_key},
        )
        p = resp.json()
        return SubmitResult(
            proposal_id=p["proposal_id"],
            status=p["status"],
            connects_cost=p["connects_cost"],
            balance_after=p.get("balance_after"),
            replayed=resp.headers.get("Idempotent-Replayed") == "true",
        )

    async def send_message(self, user, thread_id, text) -> SentMessage:
        m = (
            await self._request("POST", f"/threads/{thread_id}/messages", user, json={"text": text})
        ).json()
        return SentMessage(message_id=m["id"], thread_id=m["thread_id"], ts=m.get("ts"))

    async def health(self) -> bool:
        try:
            async with self._factory() as client:
                return (await client.get("/health")).status_code == 200
        except httpx.TransportError:
            return False


def _map_error(resp: httpx.Response) -> MarketplaceError:
    try:
        detail = resp.json().get("detail")
    except ValueError:
        detail = resp.text
    status = resp.status_code
    if status == 404:
        return NotFound(str(detail), status=status)
    if status == 402:
        return InsufficientConnects("not enough Connects", status=status, detail=detail)
    if status == 409:
        return Conflict(str(detail), status=status)
    if status == 422 and isinstance(detail, dict) and detail.get("error") == "policy_violation":
        return PolicyViolation(
            f"policy violation: {', '.join(detail.get('violations', []))}",
            status=status,
            detail=detail,
        )
    return MarketplaceError(f"GigSim {status}: {detail}", status=status, detail=detail)
