"""Load Phase 1 data into the GigSim tables (idempotent: skips if jobs already exist).

Sources: data/synthetic/{clients,jobs_stream,conversations}.jsonl, data/devset/*.jsonl and,
when present and enabled, data/heldout/*.jsonl. Gold labels and hidden client preferences are
stored in separate columns that the public API never returns.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import func, insert, select
from sqlalchemy.engine import Engine

from gigsim import db
from gigsim.settings import Settings

PUBLIC_JOB_DROP = {"_gold", "requirements", "release_minute"}
PUBLIC_CLIENT_DROP = {"_gold", "_hidden"}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").split("\n") if x]


def _job_row(job: dict, source: str) -> dict:
    public = {k: v for k, v in job.items() if k not in PUBLIC_JOB_DROP}
    gold = dict(job.get("_gold", {}))
    if "requirements" in job:  # dev/test jobs: must-have skills drive the simulated client
        gold["requirements"] = job["requirements"]
    release = int(job.get("release_minute", 0))
    return {
        "job_id": job["job_id"],
        "client_id": job["client_id"],
        "title": job["title"],
        "description": job["description"],
        "category": job.get("category"),
        "posted_at": job.get("posted_at"),
        "release_minute": release,
        "released": release == 0,
        "public": public,
        "gold": gold,
        "source": source,
    }


def load(engine: Engine, settings: Settings) -> dict:
    with engine.begin() as conn:
        if conn.execute(select(func.count()).select_from(db.jobs)).scalar_one():
            return {"skipped": True}
    d = settings.data_dir
    clients = read_jsonl(d / "synthetic" / "clients.jsonl")
    job_rows = [_job_row(j, "stream") for j in read_jsonl(d / "synthetic" / "jobs_stream.jsonl")]
    for f in sorted((d / "devset").glob("*.jsonl")):
        job_rows += [_job_row(j, "devset") for j in read_jsonl(f)]
    if settings.include_heldout and (d / "heldout").exists():
        for f in sorted((d / "heldout").glob("*.jsonl")):
            job_rows += [_job_row(j, "heldout") for j in read_jsonl(f)]
    threads = read_jsonl(d / "synthetic" / "conversations.jsonl")
    start = settings.policy["connects"]["starting_balance"]
    users = sorted(set(settings.token_map.values()))

    with engine.begin() as conn:
        conn.execute(
            insert(db.clients),
            [
                {
                    "client_id": c["client_id"],
                    "public": {k: v for k, v in c.items() if k not in PUBLIC_CLIENT_DROP},
                    "hidden": c["_hidden"],
                    "gold": c["_gold"],
                }
                for c in clients
            ],
        )
        conn.execute(insert(db.jobs), job_rows)
        conn.execute(insert(db.users), [{"user_id": u, "connects": start} for u in users])
        conn.execute(
            insert(db.ledger),
            [
                {"user_id": u, "delta": start, "reason": "starting_balance", "sim_min": 0.0}
                for u in users
            ],
        )
        thread_rows, msg_rows = [], []
        for t in threads:
            if t["persona"] not in users:
                continue
            thread_rows.append(
                {
                    "thread_id": t["thread_id"],
                    "user_id": t["persona"],
                    "client_id": t["client_id"],
                    "job_id": t["job_id"],
                    "proposal_id": None,
                    "created_min": 0.0,
                }
            )
            for m in t["messages"]:
                msg_rows.append(
                    {
                        "thread_id": t["thread_id"],
                        "sender": m["sender"],
                        "text": m["text"],
                        "ts": m["ts"],
                        "visible_min": 0.0,
                        "gold": m.get("_gold"),
                    }
                )
        if thread_rows:
            conn.execute(insert(db.threads), thread_rows)
            conn.execute(insert(db.messages), msg_rows)
    return {"clients": len(clients), "jobs": len(job_rows), "threads": len(threads), "users": users}
