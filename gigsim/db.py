"""GigSim storage: SQLAlchemy Core tables in their own `gigsim` Postgres schema.

SQLite (used by unit tests) has no schemas, so the schema name is translated away there.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

SCHEMA = "gigsim"
metadata = MetaData(schema=SCHEMA)

jobs = Table(
    "jobs",
    metadata,
    Column("job_id", String, primary_key=True),
    Column("client_id", String, index=True, nullable=False),
    Column("title", Text, nullable=False),
    Column("description", Text, nullable=False),
    Column("category", String, index=True),
    Column("posted_at", String),
    Column("release_minute", Integer, nullable=False, default=0),
    Column("released", Boolean, nullable=False, default=False, index=True),
    Column("public", JSON, nullable=False),  # everything an agent may see
    Column("gold", JSON, nullable=False),  # hidden labels (evals only)
    Column("source", String),  # stream | devset | heldout
)

clients = Table(
    "clients",
    metadata,
    Column("client_id", String, primary_key=True),
    Column("public", JSON, nullable=False),
    Column("hidden", JSON, nullable=False),
    Column("gold", JSON, nullable=False),
)

users = Table(
    "users",
    metadata,
    Column("user_id", String, primary_key=True),
    Column("connects", Integer, nullable=False),
)

proposals = Table(
    "proposals",
    metadata,
    Column("proposal_id", String, primary_key=True),
    Column("user_id", String, index=True, nullable=False),
    Column("job_id", String, index=True, nullable=False),
    Column("cover_letter", Text, nullable=False),
    Column("bid_amount", Float, nullable=False),
    Column("pay_type", String, nullable=False),
    Column("screening_answers", JSON, nullable=False),
    Column("status", String, nullable=False),  # draft | submitted
    Column("connects_cost", Integer, nullable=False),
    Column("created_min", Float, nullable=False),
    Column("submitted_min", Float),
    Column("trace_id", String),
)

idempotency = Table(
    "idempotency",
    metadata,
    Column("user_id", String, primary_key=True),
    Column("key", String, primary_key=True),
    Column("proposal_id", String, nullable=False),
    Column("response", JSON, nullable=False),
)

ledger = Table(
    "connects_ledger",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, index=True, nullable=False),
    Column("delta", Integer, nullable=False),
    Column("reason", String, nullable=False),
    Column("ref", String),
    Column("sim_min", Float, nullable=False),
)

threads = Table(
    "threads",
    metadata,
    Column("thread_id", String, primary_key=True),
    Column("user_id", String, index=True, nullable=False),
    Column("client_id", String, nullable=False),
    Column("job_id", String),
    Column("proposal_id", String),
    Column("created_min", Float, nullable=False),
)

messages = Table(
    "messages",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("thread_id", String, index=True, nullable=False),
    Column("sender", String, nullable=False),  # freelancer | client
    Column("text", Text, nullable=False),
    Column("ts", String),
    Column("visible_min", Float, nullable=False),  # message appears at this simulated minute
    Column("gold", JSON),
)

events = Table(
    "events",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, index=True, nullable=False),
    Column("proposal_id", String, index=True),
    Column("job_id", String),
    Column("type", String, nullable=False),  # viewed | replied | interview | hired | lost
    Column("due_min", Float, nullable=False, index=True),
    Column("payload", JSON, nullable=False),
)

decisions = Table(
    "decisions",
    metadata,
    Column("proposal_id", String, primary_key=True),
    Column("user_id", String, nullable=False),
    Column("job_id", String, nullable=False),
    Column("outcome", String, nullable=False),
    Column("score", Float, nullable=False),
    Column("features", JSON, nullable=False),
    Column("reasons", JSON, nullable=False),
)

meta = Table(
    "meta",
    metadata,
    Column("key", String, primary_key=True),
    Column("value", JSON, nullable=False),
    UniqueConstraint("key"),
)


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs).execution_options(schema_translate_map={SCHEMA: None})

        @event.listens_for(engine, "connect")
        def _pragma(dbapi_conn, _):  # pragma: no cover - sqlite tuning
            dbapi_conn.execute("PRAGMA journal_mode=WAL")

        return engine
    engine = create_engine(url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    return engine


def create_all(engine: Engine) -> None:
    metadata.create_all(engine)
