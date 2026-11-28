"""GigBid HTTP API.  `uv run uvicorn apps.api.main:app --reload`  (docs at /docs)

Postgres DATABASE_URL -> AsyncPostgresSaver (durable checkpoints, crash-resume) + PostgresStore
(long-term memory). SQLite / unset -> in-memory checkpointer and store (dev and tests).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
import uuid
from collections.abc import Callable
from functools import partial
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent.marketplace_port import load_config
from apps.api import db
from apps.api.deps import Service
from apps.api.routers import (
    analytics,
    approvals,
    auth,
    jobs,
    memory,
    messages,
    portfolio,
    proposals,
    runs,
    settings,
)
from apps.api.schemas import Health
from apps.api.security import TokenVault
from apps.api.service import GraphService
from apps.api.tracing import current_trace_id

log = logging.getLogger("gigbid.api")
TRACE_ID = re.compile(r"[A-Za-z0-9-]{8,64}")  # accepted X-Trace-Id values (hex, uuid)


def mcp_tokens() -> dict[str, str]:
    pairs = os.environ.get(
        "MCP_TOKENS",
        "ai_ml:dev-mcp-ai-ml,fullstack:dev-mcp-fullstack,data_analyst:dev-mcp-data-analyst",
    )
    return dict(p.split(":", 1) for p in pairs.split(",") if ":" in p)


def real_mcp_factory(config: dict) -> Callable[[str, str], Any]:
    if os.environ.get("GIGBID_MCP_MODE", "servers") == "inprocess":
        return inprocess_mcp_factory()
    from agent.mcp_client import GigBidMCPClient

    tokens = mcp_tokens()
    return lambda persona, trace_id: GigBidMCPClient(
        tokens[persona], config=config, trace_id=trace_id
    )


def inprocess_mcp_factory() -> Callable[[str, str], Any]:
    """Single-process demo hosting (GIGBID_MCP_MODE=inprocess): the same tool names and result shapes
    as the MCP servers, served in-process from the synthetic data (no Docker, Postgres or MCP servers).
    One tool layer per persona, so drafts, submissions and Connects persist for the life of the process."""
    from evals.inprocess_mcp import FakeMCP

    layers: dict[str, FakeMCP] = {}
    return lambda persona, trace_id: layers.setdefault(persona, FakeMCP(persona))


def llm_factory() -> Callable[[str], Any] | None:
    """GIGBID_AGENT_MODE=llm uses the configured models (falls back to rules per node on error)."""
    if os.environ.get("GIGBID_AGENT_MODE", "rules") != "llm":
        return None
    from agent.llm import chat_model_for_node

    return chat_model_for_node


def seed_reviewer(engine) -> None:
    email, password = os.environ.get("REVIEWER_EMAIL"), os.environ.get("REVIEWER_PASSWORD")
    if not (email and password):
        return
    from sqlalchemy import select

    from apps.api.routers.auth import create_user

    with engine.connect() as c:
        if c.execute(select(db.users.c.id).where(db.users.c.email == email.lower())).first():
            return
    create_user(engine, email, password, os.environ.get("REVIEWER_PERSONA", "ai_ml"))


@contextlib.asynccontextmanager
async def _recovery_loop(svc: GraphService, lookup: Callable[[str], dict | None], every_s: float):
    """While the API runs, restart runs that a marketplace outage halted. Not used for inline
    (serverless) hosting, where no background task survives a response."""
    if svc.inline:
        yield
        return

    async def loop() -> None:
        while True:
            await asyncio.sleep(every_s)
            try:
                await svc.recover_degraded(lookup)
            except Exception:  # noqa: BLE001 - one bad pass must not stop recovery
                log.exception("recovering degraded runs failed")

    task = asyncio.create_task(loop())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


@contextlib.asynccontextmanager
async def _durable(url: str):
    """Postgres checkpointer + store, or in-memory ones."""
    if url.startswith("postgres"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from langgraph.store.postgres import PostgresStore

        conn = url.replace("postgresql+psycopg://", "postgresql://")
        async with AsyncPostgresSaver.from_conn_string(conn) as saver:
            with PostgresStore.from_conn_string(conn) as store:
                await saver.setup()
                store.setup()
                yield saver, store
        return
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    yield InMemorySaver(), InMemoryStore()


def create_app(service_factory: Callable[[], GraphService] | None = None) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.vault = TokenVault()
        if service_factory is not None:
            app.state.service = service_factory()
            yield
            await app.state.service.wait_idle()
            return
        url = (
            os.environ.get("API_DATABASE_URL")
            or os.environ.get("DATABASE_URL")
            or "sqlite:///./var/api.db"
        )
        engine = db.make_engine(url)
        config = load_config()
        async with _durable(url) as (saver, store):
            svc = GraphService(engine, config, real_mcp_factory(config), llm=llm_factory(), checkpointer=saver, store=store,
                               inline=os.environ.get("GIGBID_INLINE_RUNS") == "1")  # fmt: skip
            app.state.service = svc
            seed_reviewer(engine)
            lookup = partial(get_user_by_id_engine, engine)
            if url.startswith("postgres"):  # resume runs that were mid-flight when the API stopped
                await svc.recover(lookup)
            async with _recovery_loop(svc, lookup, config["mcp"]["recovery_interval_s"]):
                yield

    app = FastAPI(title="GigBid API", version="0.6.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=os.environ.get("WEB_ORIGINS", "http://localhost:3000").split(","),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Trace-Id"],
    )

    @app.middleware("http")
    async def trace_ids(request, call_next):
        """One trace id per UI request (X-Trace-Id from the web client, else new), carried to the graph,
        every MCP call and the audit logs, and echoed back so the UI can show it."""
        sent = request.headers.get("x-trace-id", "")
        request.state.trace_id = sent if TRACE_ID.fullmatch(sent) else uuid.uuid4().hex
        token = current_trace_id.set(request.state.trace_id)
        try:
            response = await call_next(request)
        finally:
            current_trace_id.reset(token)
        response.headers["X-Trace-Id"] = request.state.trace_id
        return response

    routers = (auth, jobs, proposals, approvals, messages, runs, analytics, settings, memory,
               portfolio)  # fmt: skip
    for r in routers:
        app.include_router(r.router)

    @app.get("/health", response_model=Health, tags=["health"])
    async def health(svc=Service) -> Health:
        mcp = svc.mcp({"persona": "ai_ml"})
        servers = await mcp.health() if hasattr(mcp, "health") else {"marketplace": True}
        return Health(ok=True, degraded=not servers.get("marketplace", True), servers=servers)

    return app


def get_user_by_id_engine(engine, user_id: str) -> dict | None:
    from sqlalchemy import select

    with engine.connect() as c:
        row = c.execute(select(db.users).where(db.users.c.id == user_id)).mappings().first()
    return dict(row) if row else None


app = create_app()
