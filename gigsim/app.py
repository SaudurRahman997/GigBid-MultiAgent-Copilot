"""GigSim: a small simulated freelance marketplace (FastAPI).

Public API (bearer token per user):
  GET  /jobs?query&category&since&limit&offset   GET /jobs/{id}      GET /clients/{id}/history
  GET  /me/connects                              POST /proposals     POST /proposals/{id}/submit
  GET  /proposals/{id}                           GET /threads        GET /threads/{id}/messages
  POST /threads/{id}/messages                    GET /events?since   GET /policy
Admin API (admin token; for tests/evals, never given to agents):
  POST /admin/tick?minutes   GET /admin/clock   GET /admin/decisions

Behaviour: per-user token-bucket rate limit (429 + Retry-After), random simulated 5xx
(some submits are processed before the error is returned, which is exactly the case that
idempotency keys exist for), a simulated clock that releases held-back jobs, Connects
accounting, simulated client decisions and an events feed.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import re
import threading
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, insert, or_, select, update

from gigsim import db
from gigsim.client_sim import LLMRubric, decide
from gigsim.clock import SimClock
from gigsim.ratelimit import TokenBucket
from gigsim.seed import load
from gigsim.settings import Settings

SIM_EPOCH = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)  # simulated minute 0
OPEN_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


def sim_iso(minutes: float) -> str:
    return (SIM_EPOCH + timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_to_min(value: str) -> float:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (dt - SIM_EPOCH).total_seconds() / 60.0


def current_user(request: Request) -> str:
    """Set by the auth middleware; module level so FastAPI can resolve the annotation."""
    return request.state.user


User = Annotated[str, Depends(current_user)]


# ----------------------------------------------------------------------------- schemas


class ProposalDraftIn(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)
    cover_letter: str = Field(min_length=1, max_length=5000)
    bid_amount: float = Field(gt=0, le=1_000_000)
    screening_answers: dict[str, Annotated[str, Field(max_length=1500)]] = Field(
        default_factory=dict
    )


class ProposalOut(BaseModel):
    proposal_id: str
    job_id: str
    status: Literal["draft", "submitted"]
    bid_amount: float
    pay_type: str
    connects_cost: int
    cover_letter: str
    screening_answers: dict[str, str]
    created_at: str
    submitted_at: str | None = None


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


# ----------------------------------------------------------------------------- app factory


def create_app(settings: Settings | None = None, wall=None) -> FastAPI:
    settings = settings or Settings()
    engine = db.make_engine(settings.database_url)
    db.create_all(engine)
    load(engine, settings)
    clock = SimClock(engine, settings.time_scale, **({"wall": wall} if wall else {}))
    bucket = TokenBucket(settings.rate_limit_per_min)
    chaos = random.Random(f"{settings.seed}:chaos")
    chaos_lock = threading.Lock()
    llm = LLMRubric(settings) if settings.model["rubric"]["kind"] == "llm" else None
    policy = settings.policy

    def release_due() -> int:
        now = clock.now()
        with engine.begin() as conn:
            due = conn.execute(
                select(db.jobs.c.job_id, db.jobs.c.release_minute, db.jobs.c.public).where(
                    and_(db.jobs.c.released.is_(False), db.jobs.c.release_minute <= now)
                )
            ).all()
            for job_id, minute, public in due:
                conn.execute(
                    update(db.jobs)
                    .where(db.jobs.c.job_id == job_id)
                    .values(
                        released=True,
                        public={**public, "posted_at": sim_iso(minute)},
                        posted_at=sim_iso(minute),
                    )
                )
        return len(due)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        async def loop():
            while True:
                await asyncio.sleep(settings.release_interval_min * 60)
                await asyncio.to_thread(release_due)

        release_due()
        task = asyncio.create_task(loop())
        try:
            yield
        finally:
            task.cancel()

    app = FastAPI(
        title="GigSim",
        version="1.0.0",
        lifespan=lifespan,
        description="Simulated freelance marketplace for GigBid development and grading.",
    )
    app.state.settings, app.state.engine, app.state.clock = settings, engine, clock
    app.state.release_due = release_due

    # ------------------------------------------------------------------ middleware
    @app.middleware("http")
    async def gate(request: Request, call_next):
        path = request.url.path
        if path in OPEN_PATHS:
            return await call_next(request)
        auth = request.headers.get("authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        if path.startswith("/admin"):
            if token != settings.admin_token:
                return JSONResponse({"detail": "admin token required"}, status_code=401)
            return await call_next(request)
        user = settings.token_map.get(token)
        if not user:
            return JSONResponse({"detail": "invalid or missing bearer token"}, status_code=401)
        allowed, retry = bucket.take(user)
        if not allowed:
            return JSONResponse(
                {"detail": "rate limit exceeded"},
                status_code=429,
                headers={"Retry-After": str(retry)},
            )
        request.state.user = user
        with chaos_lock:
            fail = chaos.random() < settings.error_rate
            lost = chaos.random() < settings.lost_response_share
        if fail:
            if lost and request.method == "POST" and path.endswith("/submit"):
                await call_next(request)  # processed, but the client never sees the answer
                return JSONResponse({"detail": "simulated upstream error"}, status_code=502)
            return JSONResponse({"detail": "simulated outage"}, status_code=503)
        return await call_next(request)

    def violations(text: str, patterns: dict[str, str]) -> list[str]:
        return sorted(name for name, pat in patterns.items() if re.search(pat, text))

    # ------------------------------------------------------------------ helpers
    def job_or_404(conn, job_id: str):
        row = conn.execute(select(db.jobs).where(db.jobs.c.job_id == job_id)).first()
        if row is None or not row.released:
            raise HTTPException(404, "job not found")
        return row

    def connects_cost(public: dict) -> int:
        cost = int(public.get("connects_required") or 8)
        if public.get("applicants") in ("20 to 50", "50+"):
            cost *= int(policy["connects"]["multiplier_if_applicants_over_20"])
        return min(cost, int(policy["connects"]["max_per_proposal"]))

    def proposal_out(row) -> dict:
        return ProposalOut(
            proposal_id=row.proposal_id,
            job_id=row.job_id,
            status=row.status,
            bid_amount=row.bid_amount,
            pay_type=row.pay_type,
            connects_cost=row.connects_cost,
            cover_letter=row.cover_letter,
            screening_answers=row.screening_answers,
            created_at=sim_iso(row.created_min),
            submitted_at=sim_iso(row.submitted_min) if row.submitted_min is not None else None,
        ).model_dump()

    # ------------------------------------------------------------------ public endpoints
    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "policy_version": policy["version"],
            "sim_time": sim_iso(clock.now()),
        }

    @app.get("/jobs")
    def list_jobs(
        _: User,
        query: str | None = Query(None, max_length=200),
        category: str | None = None,
        since: str | None = Query(None, description="ISO time; jobs posted after it"),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
    ) -> dict:
        cond = [db.jobs.c.released.is_(True)]
        if query:
            for term in query.split()[:6]:
                like = f"%{term}%"
                cond.append(or_(db.jobs.c.title.ilike(like), db.jobs.c.description.ilike(like)))
        if category:
            cond.append(db.jobs.c.category == category)
        if since:
            cond.append(db.jobs.c.posted_at > sim_iso(iso_to_min(since)))
        with engine.connect() as conn:
            total = conn.execute(
                select(func.count()).select_from(db.jobs).where(*cond)
            ).scalar_one()
            rows = conn.execute(
                select(db.jobs.c.public)
                .where(*cond)
                .order_by(db.jobs.c.posted_at.desc(), db.jobs.c.job_id)
                .limit(limit)
                .offset(offset)
            ).all()
        return {"total": total, "items": [r.public for r in rows], "limit": limit, "offset": offset}

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str, _: User) -> dict:
        with engine.connect() as conn:
            return job_or_404(conn, job_id).public

    @app.get("/clients/{client_id}/history")
    def client_history(client_id: str, _: User) -> dict:
        with engine.connect() as conn:
            row = conn.execute(
                select(db.clients.c.public).where(db.clients.c.client_id == client_id)
            ).first()
        if row is None:
            raise HTTPException(404, "client not found")
        return row.public

    @app.get("/me/connects")
    def my_connects(user: User) -> dict:
        with engine.connect() as conn:
            bal = conn.execute(
                select(db.users.c.connects).where(db.users.c.user_id == user)
            ).scalar_one()
            led = conn.execute(
                select(db.ledger)
                .where(db.ledger.c.user_id == user)
                .order_by(db.ledger.c.id.desc())
                .limit(20)
            ).all()
        return {
            "user": user,
            "balance": bal,
            "ledger": [
                {"delta": x.delta, "reason": x.reason, "ref": x.ref, "at": sim_iso(x.sim_min)}
                for x in led
            ],
        }

    @app.post("/proposals", status_code=201)
    def create_draft(body: ProposalDraftIn, user: User) -> dict:
        bad = violations(
            body.cover_letter + " " + " ".join(body.screening_answers.values()),
            policy["proposals"]["blocked_patterns"],
        )
        if bad:
            raise HTTPException(
                422,
                {
                    "error": "policy_violation",
                    "violations": bad,
                    "policy_version": policy["version"],
                },
            )
        with engine.begin() as conn:
            job = job_or_404(conn, body.job_id)
            n = conn.execute(select(func.count()).select_from(db.proposals)).scalar_one() + 1
            row = {
                "proposal_id": f"pr_{n:06d}",
                "user_id": user,
                "job_id": body.job_id,
                "cover_letter": body.cover_letter,
                "bid_amount": body.bid_amount,
                "pay_type": job.public.get("pay_type", "fixed"),
                "screening_answers": body.screening_answers,
                "status": "draft",
                "connects_cost": connects_cost(job.public),
                "created_min": clock.now(),
            }
            conn.execute(insert(db.proposals).values(**row))
            out = conn.execute(
                select(db.proposals).where(db.proposals.c.proposal_id == row["proposal_id"])
            ).first()
        return proposal_out(out)

    @app.get("/proposals/{proposal_id}")
    def get_proposal(proposal_id: str, user: User) -> dict:
        with engine.connect() as conn:
            row = conn.execute(
                select(db.proposals).where(
                    db.proposals.c.proposal_id == proposal_id, db.proposals.c.user_id == user
                )
            ).first()
        if row is None:
            raise HTTPException(404, "proposal not found")
        return proposal_out(row)

    @app.post("/proposals/{proposal_id}/submit")
    def submit(
        proposal_id: str,
        user: User,
        idempotency_key: Annotated[
            str | None, Header(alias="Idempotency-Key", max_length=200)
        ] = None,
    ) -> JSONResponse:
        if not idempotency_key:
            raise HTTPException(400, "Idempotency-Key header is required")
        with engine.begin() as conn:
            prior = conn.execute(
                select(db.idempotency).where(
                    db.idempotency.c.user_id == user, db.idempotency.c.key == idempotency_key
                )
            ).first()
            if prior is not None:
                if prior.proposal_id != proposal_id:
                    raise HTTPException(
                        409, "Idempotency-Key already used for a different proposal"
                    )
                return JSONResponse(prior.response, headers={"Idempotent-Replayed": "true"})
            prop = conn.execute(
                select(db.proposals).where(
                    db.proposals.c.proposal_id == proposal_id, db.proposals.c.user_id == user
                )
            ).first()
            if prop is None:
                raise HTTPException(404, "proposal not found")
            if prop.status != "draft":
                raise HTTPException(
                    409, "proposal already submitted (use the original Idempotency-Key to replay)"
                )
            if not policy["proposals"]["external_links_allowed"]:
                bad = violations(prop.cover_letter, policy["proposals"]["blocked_patterns"])
                if bad:
                    raise HTTPException(
                        422,
                        {
                            "error": "policy_violation",
                            "violations": bad,
                            "policy_version": policy["version"],
                        },
                    )
            job = conn.execute(select(db.jobs).where(db.jobs.c.job_id == prop.job_id)).first()
            balance = conn.execute(
                select(db.users.c.connects).where(db.users.c.user_id == user)
            ).scalar_one()
            cost = connects_cost(job.public)
            if balance < cost:
                raise HTTPException(
                    402, {"error": "insufficient_connects", "balance": balance, "cost": cost}
                )
            now = clock.now()
            conn.execute(
                update(db.users).where(db.users.c.user_id == user).values(connects=balance - cost)
            )
            conn.execute(
                insert(db.ledger).values(
                    user_id=user,
                    delta=-cost,
                    reason="submit_proposal",
                    ref=proposal_id,
                    sim_min=now,
                )
            )
            conn.execute(
                update(db.proposals)
                .where(db.proposals.c.proposal_id == proposal_id)
                .values(status="submitted", submitted_min=now, connects_cost=cost)
            )
            client = conn.execute(
                select(db.clients).where(db.clients.c.client_id == job.client_id)
            ).first()
            dec = decide(
                settings,
                user,
                job.public,
                job.gold,
                client.hidden,
                prop.cover_letter,
                prop.screening_answers,
                prop.bid_amount,
                llm,
            )
            conn.execute(
                insert(db.decisions).values(
                    proposal_id=proposal_id,
                    user_id=user,
                    job_id=job.job_id,
                    outcome=dec.outcome,
                    score=dec.score,
                    features={**dec.features, "p": dec.p},
                    reasons=dec.reasons,
                )
            )
            for ev in dec.events:
                conn.execute(
                    insert(db.events).values(
                        user_id=user,
                        proposal_id=proposal_id,
                        job_id=job.job_id,
                        type=ev["type"],
                        due_min=now + ev["delay_min"],
                        payload=ev.get("payload", {}),
                    )
                )
            if dec.client_messages:
                thread_id = f"th_{proposal_id}"
                conn.execute(
                    insert(db.threads).values(
                        thread_id=thread_id,
                        user_id=user,
                        client_id=job.client_id,
                        job_id=job.job_id,
                        proposal_id=proposal_id,
                        created_min=now,
                    )
                )
                for msg in dec.client_messages:
                    t = now + msg["delay_min"]
                    conn.execute(
                        insert(db.messages).values(
                            thread_id=thread_id,
                            sender="client",
                            text=msg["text"],
                            ts=sim_iso(t),
                            visible_min=t,
                        )
                    )
            out = conn.execute(
                select(db.proposals).where(db.proposals.c.proposal_id == proposal_id)
            ).first()
            response = {**proposal_out(out), "balance_after": balance - cost}
            conn.execute(
                insert(db.idempotency).values(
                    user_id=user, key=idempotency_key, proposal_id=proposal_id, response=response
                )
            )
        return JSONResponse(response)

    @app.get("/threads")
    def list_threads(user: User) -> dict:
        now = clock.now()
        with engine.connect() as conn:
            rows = conn.execute(
                select(db.threads)
                .where(db.threads.c.user_id == user)
                .order_by(db.threads.c.thread_id)
            ).all()
            items = []
            for t in rows:
                last = conn.execute(
                    select(db.messages)
                    .where(db.messages.c.thread_id == t.thread_id, db.messages.c.visible_min <= now)
                    .order_by(db.messages.c.id.desc())
                    .limit(1)
                ).first()
                if last is None:
                    continue  # a client reply scheduled in the future: thread not visible yet
                items.append(
                    {
                        "thread_id": t.thread_id,
                        "client_id": t.client_id,
                        "job_id": t.job_id,
                        "proposal_id": t.proposal_id,
                        "last_message": {"sender": last.sender, "text": last.text, "ts": last.ts},
                    }
                )
        return {"items": items}

    def thread_or_404(conn, thread_id: str, user: str):
        t = conn.execute(
            select(db.threads).where(
                db.threads.c.thread_id == thread_id, db.threads.c.user_id == user
            )
        ).first()
        if t is None:
            raise HTTPException(404, "thread not found")
        return t

    @app.get("/threads/{thread_id}/messages")
    def thread_messages(thread_id: str, user: User) -> dict:
        now = clock.now()
        with engine.connect() as conn:
            thread_or_404(conn, thread_id, user)
            rows = conn.execute(
                select(db.messages)
                .where(db.messages.c.thread_id == thread_id, db.messages.c.visible_min <= now)
                .order_by(db.messages.c.id)
            ).all()
        return {
            "thread_id": thread_id,
            "items": [
                {"id": f"m{x.id}", "sender": x.sender, "text": x.text, "ts": x.ts} for x in rows
            ],
        }

    @app.post("/threads/{thread_id}/messages", status_code=201)
    def send_message(thread_id: str, body: MessageIn, user: User) -> dict:
        bad = violations(body.text, policy["messages"]["blocked_patterns"])
        if bad:
            raise HTTPException(
                422,
                {
                    "error": "policy_violation",
                    "violations": bad,
                    "policy_version": policy["version"],
                },
            )
        now = clock.now()
        with engine.begin() as conn:
            thread_or_404(conn, thread_id, user)
            res = conn.execute(
                insert(db.messages).values(
                    thread_id=thread_id,
                    sender="freelancer",
                    text=body.text,
                    ts=sim_iso(now),
                    visible_min=now,
                )
            )
        return {
            "id": f"m{res.inserted_primary_key[0]}",
            "thread_id": thread_id,
            "sender": "freelancer",
            "text": body.text,
            "ts": sim_iso(now),
        }

    @app.get("/events")
    def list_events(
        user: User,
        since: str | None = Query(None, description="ISO time cursor (exclusive)"),
        limit: int = Query(200, ge=1, le=1000),
    ) -> dict:
        now = clock.now()
        lo = iso_to_min(since) if since else float("-inf")
        with engine.connect() as conn:
            rows = conn.execute(
                select(db.events)
                .where(
                    db.events.c.user_id == user,
                    db.events.c.due_min > lo,
                    db.events.c.due_min <= now,
                )
                .order_by(db.events.c.due_min, db.events.c.id)
                .limit(limit)
            ).all()
        items = [
            {
                "id": f"ev{x.id}",
                "type": x.type,
                "proposal_id": x.proposal_id,
                "job_id": x.job_id,
                "at": sim_iso(x.due_min),
                "payload": x.payload,
            }
            for x in rows
        ]
        nxt = items[-1]["at"] if len(items) == limit else sim_iso(now)
        return {"items": items, "next_since": nxt}

    @app.get("/policy")
    def get_policy(_: User) -> dict:
        return {
            "version": policy["version"],
            "connects": policy["connects"],
            "proposals": policy["proposals"],
            "messages": policy["messages"],
        }

    # ------------------------------------------------------------------ admin
    @app.post("/admin/tick")
    def tick(minutes: float = Query(..., gt=0, le=60 * 24 * 30)) -> dict:
        now = clock.advance(minutes)
        return {"sim_time": sim_iso(now), "released": release_due()}

    @app.get("/admin/clock")
    def admin_clock() -> dict:
        return {"sim_minutes": clock.now(), "sim_time": sim_iso(clock.now())}

    @app.get("/admin/decisions")
    def admin_decisions(user: str | None = None) -> dict:
        with engine.connect() as conn:
            q = select(db.decisions).order_by(db.decisions.c.proposal_id)
            if user:
                q = q.where(db.decisions.c.user_id == user)
            rows = conn.execute(q).all()
        return {"items": [dict(r._mapping) for r in rows]}

    return app


def main() -> None:  # pragma: no cover - container entry point
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8100)


if __name__ == "__main__":  # pragma: no cover
    main()
