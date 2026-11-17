"""Worker jobs: saved-search scheduling slots, dedupe, interval floors, idempotent analysis, polling."""

from __future__ import annotations

import copy

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from agent.marketplace_port import load_config
from apps.api import db
from apps.api.routers.auth import create_user
from apps.api.service import GraphService
from apps.worker import jobs
from apps.worker.main import WorkerSettings
from tests.fakes import FakeMCP

pytestmark = pytest.mark.anyio
T0 = 1_800_000_000.0  # a fixed "now" (seconds)


class FakeArqRedis:
    """Arq semantics that matter here: a job id that was already enqueued is not enqueued again."""

    def __init__(self):
        self.jobs: list[tuple[str, tuple, str]] = []

    async def enqueue_job(self, fn: str, *args, _job_id: str | None = None):
        if _job_id and any(j[2] == _job_id for j in self.jobs):
            return None
        self.jobs.append((fn, args, _job_id or f"auto{len(self.jobs)}"))
        return object()


@pytest.fixture
def ctx(tmp_path):
    engine = db.make_engine(f"sqlite:///{(tmp_path / 'w.db').as_posix()}")
    fakes: dict[str, FakeMCP] = {}
    svc = GraphService(engine, load_config(), lambda persona, trace: fakes.setdefault(persona, FakeMCP(persona)),
                       checkpointer=InMemorySaver(), store=InMemoryStore(), inline=True)  # fmt: skip
    user = create_user(engine, "fl@example.com", "pass-12345678", "ai_ml")
    with engine.begin() as c:
        c.execute(
            db.settings.insert().values(
                tenant_id=user["id"],
                value={"saved_searches": [{"name": "all", "query": "", "every_minutes": 30}]},
            )
        )
    return {
        "redis": FakeArqRedis(),
        "service": svc,
        "config": load_config(),
        "user": user,
        "fakes": fakes,
    }


def test_interval_respects_the_marketplace_floor():
    cfg = load_config()
    live = {**copy.deepcopy(cfg), "marketplace": "upwork_live"}
    assert jobs.interval_minutes({"every_minutes": 30}, cfg) == max(
        30, cfg["scheduling"]["gigsim_interval_min"]
    )
    assert (
        jobs.interval_minutes({"every_minutes": 30}, live)
        == cfg["scheduling"]["live_interval_min"]
        == 60
    )
    assert jobs.interval_minutes({"every_minutes": 120}, live) == 120


async def test_each_search_runs_once_per_interval_slot(ctx):
    assert await jobs.schedule_saved_searches(ctx, now_s=T0) == 1
    assert await jobs.schedule_saved_searches(ctx, now_s=T0 + 60) == 0  # same 30-minute slot
    assert await jobs.schedule_saved_searches(ctx, now_s=T0 + 30 * 60) == 1  # next slot
    assert [j[0] for j in ctx["redis"].jobs] == ["run_saved_search", "run_saved_search"]


async def test_saved_search_enqueues_each_job_once_per_user(ctx):
    uid = ctx["user"]["id"]
    n = await jobs.run_saved_search(ctx, uid, {"name": "all", "query": ""})
    assert n == 20 and all(j[2].startswith(f"analyze:{uid}:") for j in ctx["redis"].jobs)
    assert (
        await jobs.run_saved_search(ctx, uid, {"name": "all", "query": ""}) == 0
    )  # dedupe key = user + job id


async def test_analyze_is_idempotent_and_stops_at_approval(ctx):
    import json
    from pathlib import Path

    job = next(json.loads(x) for x in (Path(__file__).resolve().parents[2] / "data/devset/ai_ml.jsonl").read_text(encoding="utf-8").splitlines()
               if json.loads(x)["_gold"]["bid"] == "bid")  # fmt: skip
    uid = ctx["user"]["id"]
    tid = await jobs.analyze_job(ctx, uid, job["job_id"], job["title"])
    assert tid and ctx["service"].run_row(ctx["user"], tid)["status"] == "awaiting_approval"
    assert (
        await jobs.analyze_job(ctx, uid, job["job_id"], job["title"]) is None
    )  # already has a run
    assert ctx["fakes"]["ai_ml"].submits == 0  # nothing is sent without a human


async def test_poll_messages_starts_one_reply_per_new_client_message(ctx):
    assert await jobs.poll_messages(ctx) == 1  # FakeMCP thread th_test ends with a client message
    assert await jobs.poll_messages(ctx) == 0
    fn, args, job_id = ctx["redis"].jobs[0]
    assert fn == "reply_to_thread" and args[1] == "th_test" and job_id.endswith(":th_test:m2")
    tid = await jobs.reply_to_thread(ctx, *args)
    assert ctx["service"].run_row(ctx["user"], tid)["status"] == "awaiting_approval"


def test_worker_settings_register_every_job():
    names = {f.__name__ for f in WorkerSettings.functions}
    assert names == {"run_saved_search", "analyze_job", "reply_to_thread"}
    assert len(WorkerSettings.cron_jobs) == 2
