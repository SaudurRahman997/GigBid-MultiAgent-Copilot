"""Workspace MCP server: calendar availability, tentative holds and email DRAFTS (local mock).

Tools  free_slots(start, end, duration_min)                         read-only
       create_tentative_hold(start, duration_min, title, idempotency_key, dry_run)
       create_email_draft(to, subject, body, idempotency_key, dry_run)   (never sends)
The calendar is a deterministic mock: weekday working hours 09:00-17:00 UTC minus seeded busy
blocks and existing holds. Google Calendar/Gmail could replace the mock behind the same tools.
"""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime, timedelta
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field
from sqlalchemy import JSON, Column, MetaData, String, Table, insert, select

from mcp_servers.common.runtime import TokenBucket, ToolRunner, make_server
from mcp_servers.common.settings import MCPSettings
from mcp_servers.common.store import SCHEMA, Store

SERVER = "workspace"
PORT = 8203
WORK_START_H, WORK_END_H = 9, 17
GRID_MIN = 30
MAX_RANGE_DAYS = 14
MAX_SLOTS = 20
INSTRUCTIONS = (
    "Calendar availability, tentative holds and email drafts for the freelancer. Nothing is "
    "sent: holds are tentative and emails stay drafts until the freelancer acts on them."
)

ws_metadata = MetaData(schema=SCHEMA)
holds = Table(
    "workspace_holds",
    ws_metadata,
    Column("hold_id", String, primary_key=True),
    Column("user", String, index=True, nullable=False),
    Column("start", String, nullable=False),
    Column("end", String, nullable=False),
    Column("title", String, nullable=False),
)
email_drafts = Table(
    "workspace_email_drafts",
    ws_metadata,
    Column("draft_id", String, primary_key=True),
    Column("user", String, index=True, nullable=False),
    Column("payload", JSON, nullable=False),
)

IdemKey = Annotated[str, Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9:_.\-]+$")]
DryRun = Annotated[bool, Field(description="If true, validate and preview only")]
IsoTime = Annotated[str, Field(min_length=10, max_length=40, description="ISO 8601, UTC assumed")]
WRITE = ToolAnnotations(
    readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False
)


class Slot(BaseModel):
    start: str
    end: str


class SlotsResult(BaseModel):
    slots: list[Slot]
    timezone: str = "UTC"


class Hold(BaseModel):
    dry_run: bool
    hold_id: str | None
    start: str
    end: str
    title: str
    status: str = "tentative"
    replayed: bool = False


class EmailDraft(BaseModel):
    dry_run: bool
    draft_id: str | None
    to: str
    subject: str
    body_preview: str
    status: str = "draft"
    replayed: bool = False


def parse_time(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ToolError(f"invalid_time: {value!r} is not ISO 8601") from exc
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def busy_blocks(user: str, day: datetime) -> list[tuple[datetime, datetime]]:
    """Deterministic mock meetings for one user and day (seeded by user + date)."""
    seed = hashlib.sha256(f"{user}:{day:%Y-%m-%d}".encode()).hexdigest()
    r = random.Random(seed)
    blocks = []
    for _ in range(r.randint(1, 3)):
        start = day.replace(hour=r.randint(WORK_START_H, WORK_END_H - 2), minute=r.choice([0, 30]))
        blocks.append((start, start + timedelta(minutes=r.choice([30, 60, 90]))))
    return blocks


def build_server(settings: MCPSettings | None = None, store: Store | None = None) -> FastMCP:
    s = settings or MCPSettings()
    db = store or Store(s.database_url, extra_metadata=[ws_metadata])
    if store is not None:
        ws_metadata.create_all(db.engine)
    runner = ToolRunner(SERVER, s, db, TokenBucket(s.rate_limit_per_min))
    mcp = make_server("gigbid-workspace", INSTRUCTIONS, s, PORT)

    def user_holds(user: str) -> list[tuple[datetime, datetime]]:
        with db.engine.connect() as conn:
            rows = conn.execute(select(holds.c.start, holds.c.end).where(holds.c.user == user))
            return [(parse_time(a), parse_time(b)) for a, b in rows]

    def is_free(user: str, start: datetime, end: datetime) -> bool:
        if start.weekday() >= 5 or start.hour < WORK_START_H:
            return False
        if end > start.replace(hour=WORK_END_H, minute=0, second=0, microsecond=0):
            return False
        day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        taken = busy_blocks(user, day) + user_holds(user)
        return all(end <= a or start >= b for a, b in taken)

    @mcp.tool(
        title="Find free calendar slots",
        annotations=ToolAnnotations(
            readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
        ),
    )
    async def free_slots(
        start: IsoTime,
        end: IsoTime,
        duration_min: Annotated[int, Field(ge=15, le=240)] = 30,
        ctx: Context | None = None,
    ) -> SlotsResult:
        """Free slots between start and end (max 14 days), on a 30-minute grid, working hours
        09:00-17:00 UTC on weekdays. Returns at most 20 slots."""

        async def fn(user: str) -> SlotsResult:
            a, b = parse_time(start), parse_time(end)
            if b <= a or b - a > timedelta(days=MAX_RANGE_DAYS):
                raise ToolError("invalid_range: end must be after start and within 14 days")
            t = a.replace(minute=(a.minute // GRID_MIN) * GRID_MIN, second=0, microsecond=0)
            if t < a:
                t += timedelta(minutes=GRID_MIN)
            out: list[Slot] = []
            while t + timedelta(minutes=duration_min) <= b and len(out) < MAX_SLOTS:
                e = t + timedelta(minutes=duration_min)
                if is_free(user, t, e):
                    out.append(Slot(start=iso(t), end=iso(e)))
                t += timedelta(minutes=GRID_MIN)
            return SlotsResult(slots=out)

        args = {"start": start, "end": end, "duration_min": duration_min}
        return await runner.run("free_slots", args, ctx, fn, lambda r: f"{len(r.slots)} slots")

    @mcp.tool(title="Create tentative calendar hold", annotations=WRITE)
    async def create_tentative_hold(
        start: IsoTime,
        duration_min: Annotated[int, Field(ge=15, le=240)],
        title: Annotated[str, Field(min_length=1, max_length=120)],
        idempotency_key: IdemKey,
        dry_run: DryRun = False,
        ctx: Context | None = None,
    ) -> Hold:
        """Reserve a slot tentatively (e.g. a proposed interview time). Fails if not free."""
        args = {
            "start": start,
            "duration_min": duration_min,
            "title": title,
            "idempotency_key": idempotency_key,
            "dry_run": dry_run,
        }

        async def fn(user: str) -> Hold:
            a = parse_time(start)
            e = a + timedelta(minutes=duration_min)

            async def do() -> Hold:
                if not is_free(user, a, e):
                    raise ToolError("slot_unavailable: that time is not free")
                hold_id = (
                    "hold_" + hashlib.sha1(f"{user}:{idempotency_key}".encode()).hexdigest()[:12]
                )
                with db.engine.begin() as conn:
                    conn.execute(
                        insert(holds).values(
                            hold_id=hold_id, user=user, start=iso(a), end=iso(e), title=title
                        )
                    )
                return Hold(dry_run=False, hold_id=hold_id, start=iso(a), end=iso(e), title=title)

            if dry_run:
                if not is_free(user, a, e):
                    raise ToolError("slot_unavailable: that time is not free")
                return Hold(dry_run=True, hold_id=None, start=iso(a), end=iso(e), title=title)
            return await runner.idempotent(
                user, "create_tentative_hold", idempotency_key, args, Hold, do
            )

        return await runner.run(
            "create_tentative_hold", args, ctx, fn, lambda r: f"hold {r.hold_id} {r.start}"
        )

    @mcp.tool(title="Create email draft (not sent)", annotations=WRITE)
    async def create_email_draft(
        to: Annotated[str, Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")],
        subject: Annotated[str, Field(min_length=1, max_length=200)],
        body: Annotated[str, Field(min_length=1, max_length=10_000)],
        idempotency_key: IdemKey,
        dry_run: DryRun = False,
        ctx: Context | None = None,
    ) -> EmailDraft:
        """Save an email DRAFT for the freelancer to review. Never sends. Marketplace clients
        must be contacted on-platform (policy), so use this for the freelancer's own notes."""
        args = {
            "to": to,
            "subject": subject,
            "body": body,
            "idempotency_key": idempotency_key,
            "dry_run": dry_run,
        }

        async def fn(user: str) -> EmailDraft:
            preview = body[:200]
            if dry_run:
                return EmailDraft(
                    dry_run=True, draft_id=None, to=to, subject=subject, body_preview=preview
                )

            async def do() -> EmailDraft:
                draft_id = (
                    "draft_" + hashlib.sha1(f"{user}:{idempotency_key}".encode()).hexdigest()[:12]
                )
                with db.engine.begin() as conn:
                    conn.execute(
                        insert(email_drafts).values(
                            draft_id=draft_id,
                            user=user,
                            payload={"to": to, "subject": subject, "body": body},
                        )
                    )
                return EmailDraft(
                    dry_run=False, draft_id=draft_id, to=to, subject=subject, body_preview=preview
                )

            return await runner.idempotent(
                user, "create_email_draft", idempotency_key, args, EmailDraft, do
            )

        return await runner.run(
            "create_email_draft", args, ctx, fn, lambda r: f"draft {r.draft_id}"
        )

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request):  # pragma: no cover - exercised in docker
        from starlette.responses import JSONResponse

        return JSONResponse({"status": "ok", "server": SERVER})

    mcp.store = db  # type: ignore[attr-defined]
    return mcp
