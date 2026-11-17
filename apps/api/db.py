"""API tables (schema `app`): users, runs, settings, encrypted OAuth tokens.

Every row that belongs to a user carries `tenant_id`; every query in the routers filters on it.
SQLite (tests, local) maps the schema away, Postgres creates it.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
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

SCHEMA = "app"
metadata = MetaData(schema=SCHEMA)


def now() -> datetime:
    return datetime.now(UTC)


users = Table(
    "users",
    metadata,
    Column("id", String, primary_key=True),
    Column("email", String, nullable=False, unique=True),
    Column("password_hash", String, nullable=False),
    Column("persona", String, nullable=False),
    Column("created_at", DateTime(timezone=True), default=now),
)

runs = Table(
    "runs",
    metadata,
    Column("thread_id", String, primary_key=True),
    Column("tenant_id", String, nullable=False, index=True),
    Column("kind", String, nullable=False),  # bid | conversation
    Column("subject", String, nullable=False),  # job id or marketplace thread id
    Column("title", String, nullable=False, default=""),
    Column("status", String, nullable=False, default="queued"),
    Column("stage", String, nullable=True),  # pipeline column (drafted, submitted, ...)
    Column("tokens", Integer, nullable=False, default=0),
    Column("steps", Integer, nullable=False, default=0),
    Column("summary", JSON, nullable=False, default=dict),
    Column("created_at", DateTime(timezone=True), default=now),
    Column("updated_at", DateTime(timezone=True), default=now, onupdate=now),
)

settings = Table(
    "settings",
    metadata,
    Column("tenant_id", String, primary_key=True),
    Column("value", JSON, nullable=False),
)

oauth_tokens = Table(
    "oauth_tokens",
    metadata,
    Column("tenant_id", String, nullable=False),
    Column("provider", String, nullable=False),
    Column("ciphertext", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), default=now, onupdate=now),
    UniqueConstraint("tenant_id", "provider"),
)


def make_engine(url: str) -> Engine:
    url = (
        url.replace("postgresql://", "postgresql+psycopg://", 1)
        if url.startswith("postgresql://")
        else url
    )
    if url.startswith("sqlite"):
        kwargs: dict = {"connect_args": {"check_same_thread": False}}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kwargs["poolclass"] = StaticPool
        engine = create_engine(url, **kwargs).execution_options(schema_translate_map={SCHEMA: None})

        @event.listens_for(engine, "connect")
        def _pragma(dbapi_conn, _):  # pragma: no cover - sqlite tuning
            dbapi_conn.execute("PRAGMA journal_mode=WAL")

    else:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.begin() as conn:
            conn.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    metadata.create_all(engine)
    return engine
