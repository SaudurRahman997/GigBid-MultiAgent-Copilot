"""Arq worker settings. Run: uv run arq apps.worker.main.WorkerSettings  (needs REDIS_URL).

Shares the API's database, checkpointer and store (API_DATABASE_URL / DATABASE_URL), so runs it
starts appear in the UI and their approvals resume from the API. Graph runs execute inline inside the
Arq job (GraphService(inline=True)), so a job finishes when its graph reaches approval or the end.
"""

from __future__ import annotations

import contextlib
import os

from arq import cron
from arq.connections import RedisSettings

from agent.marketplace_port import load_config
from apps.api import db
from apps.api.main import _durable, llm_factory, real_mcp_factory
from apps.api.service import GraphService
from apps.worker.jobs import (
    analyze_job,
    poll_messages,
    reply_to_thread,
    run_saved_search,
    schedule_saved_searches,
)


async def startup(ctx: dict) -> None:
    url = (
        os.environ.get("API_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "sqlite:///./var/api.db"
    )
    config = load_config()
    stack = contextlib.AsyncExitStack()
    saver, store = await stack.enter_async_context(_durable(url))
    ctx.update(stack=stack, config=config,
               service=GraphService(db.make_engine(url), config, real_mcp_factory(config), llm=llm_factory(),
                                    checkpointer=saver, store=store, inline=True))  # fmt: skip


async def shutdown(ctx: dict) -> None:
    await ctx["stack"].aclose()


class WorkerSettings:
    functions = [run_saved_search, analyze_job, reply_to_thread]
    cron_jobs = [
        cron(
            schedule_saved_searches, second=0
        ),  # every minute; each search runs once per its interval slot
        cron(poll_messages, minute=set(range(0, 60, 5)), second=30),
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    max_jobs = 4
    job_timeout = 900
