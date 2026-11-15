"""Shared storage for the MCP servers: append-only audit log + idempotency records.

On Postgres the tables live in the `gigbid` schema and a trigger rejects UPDATE/DELETE on the
audit log, so it is append-only at the database level, not only by convention.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

from mcp_servers.common.masking import mask

SCHEMA = "gigbid"
metadata = MetaData(schema=SCHEMA)

audit_log = Table(
    "mcp_audit_log",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("ts", String, nullable=False),
    Column("user", String, nullable=False, index=True),
    Column("server", String, nullable=False),
    Column("tool", String, nullable=False, index=True),
    Column("args_masked", JSON, nullable=False),
    Column("result_summary", Text, nullable=False),
    Column("status", String, nullable=False),  # ok | error | dry_run | replayed
    Column("trace_id", String, index=True),
)

idempotency = Table(
    "mcp_idempotency",
    metadata,
    Column("server", String, primary_key=True),
    Column("user", String, primary_key=True),
    Column("tool", String, primary_key=True),
    Column("key", String, primary_key=True),
    Column("request_hash", String, nullable=False),
    Column("result", JSON, nullable=False),
    Column("ts", String, nullable=False),
)

APPEND_ONLY_DDL = f"""
CREATE OR REPLACE FUNCTION {SCHEMA}.mcp_audit_no_change() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'mcp_audit_log is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS mcp_audit_append_only ON {SCHEMA}.mcp_audit_log;
CREATE TRIGGER mcp_audit_append_only BEFORE UPDATE OR DELETE ON {SCHEMA}.mcp_audit_log
FOR EACH ROW EXECUTE FUNCTION {SCHEMA}.mcp_audit_no_change();
"""


class IdempotencyConflict(Exception):
    """Same idempotency key reused with different arguments."""


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def request_hash(args: dict) -> str:
    clean = {k: v for k, v in args.items() if k not in {"dry_run", "idempotency_key"}}
    return hashlib.sha256(json.dumps(clean, sort_keys=True, default=str).encode()).hexdigest()


class Store:
    def __init__(self, url: str, extra_metadata: list[MetaData] | None = None):
        if url.startswith("sqlite"):
            kw: dict = {"connect_args": {"check_same_thread": False}}
            if url in ("sqlite://", "sqlite:///:memory:"):
                kw["poolclass"] = StaticPool
            self.engine: Engine = create_engine(url, **kw).execution_options(
                schema_translate_map={SCHEMA: None}
            )
            self.postgres = False
        else:
            self.engine = create_engine(url, pool_pre_ping=True)
            self.postgres = True
            with self.engine.begin() as conn:
                conn.exec_driver_sql(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
        metadata.create_all(self.engine)
        for md in extra_metadata or []:
            md.create_all(self.engine)
        if self.postgres:
            with self.engine.begin() as conn:
                conn.exec_driver_sql(APPEND_ONLY_DDL)

    # ------------------------------------------------------------------ audit
    def audit(
        self,
        *,
        user: str,
        server: str,
        tool: str,
        args: dict,
        result_summary: str,
        status: str,
        trace_id: str | None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                insert(audit_log).values(
                    ts=now_iso(),
                    user=user,
                    server=server,
                    tool=tool,
                    args_masked=mask(args),
                    result_summary=mask(result_summary)[:1000],
                    status=status,
                    trace_id=trace_id,
                )
            )

    def audit_rows(self, user: str | None = None) -> list[dict]:
        q = select(audit_log).order_by(audit_log.c.id)
        if user:
            q = q.where(audit_log.c.user == user)
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(q)]

    # ------------------------------------------------------------------ idempotency
    def recall(self, server: str, user: str, tool: str, key: str, args: dict) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(idempotency).where(
                    idempotency.c.server == server,
                    idempotency.c.user == user,
                    idempotency.c.tool == tool,
                    idempotency.c.key == key,
                )
            ).first()
        if row is None:
            return None
        if row.request_hash != request_hash(args):
            raise IdempotencyConflict(
                f"idempotency_key {key!r} was already used with different arguments"
            )
        return dict(row.result)

    def remember(
        self, server: str, user: str, tool: str, key: str, args: dict, result: dict[str, Any]
    ) -> dict:
        try:
            with self.engine.begin() as conn:
                conn.execute(
                    insert(idempotency).values(
                        server=server,
                        user=user,
                        tool=tool,
                        key=key,
                        request_hash=request_hash(args),
                        result=result,
                        ts=now_iso(),
                    )
                )
        except IntegrityError:  # concurrent duplicate: the first writer wins
            return self.recall(server, user, tool, key, args) or result
        return result
