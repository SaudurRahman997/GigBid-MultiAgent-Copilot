"""R&D C - is multi-agent worth it?

Same 50 dev jobs (seeded, stratified by persona), same model, same in-process tools, three systems:
  react       one ReAct agent with all tools            (langgraph.prebuilt.create_react_agent)
  supervisor  langgraph-supervisor with 3 ReAct workers  (analyst / researcher / writer)
  graph       GigBid's hand-written bid graph (LLM nodes per agent/config.yaml), up to approval

Per system: bid/skip accuracy + macro-F1 + scam P/R (same metric code as decision_eval),
unsupported-claim rate of the letters (portfolio verifier), letters that would reach the human
with a policy violation (compliance filter), simulated reply rate (fresh in-process GigSim,
chaos off, 30 simulated days), tokens/job and latency/job.

Writes evals/results/multiagent/<system>.json (+ .jobs.jsonl) and evals/results/multiagent/summary.json.

Usage:
  uv run python -m evals.runners.multiagent_eval --systems graph react supervisor [--jobs 50]
  (model: --provider ollama --model llama3.2:3b by default; overrides the config roles via env)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "results" / "multiagent"
SEED = 20261115
PERSONAS = ("ai_ml", "fullstack", "data_analyst")


def sample_jobs(n: int) -> list[dict]:
    from evals.runners.rag_eval import read_jobs

    rng = random.Random(SEED)
    per = [n // 3 + (1 if i < n % 3 else 0) for i in range(3)]
    out = []
    for persona, k in zip(PERSONAS, per, strict=True):
        jobs = read_jobs("dev", persona)
        out += [{**j, "_persona": persona} for j in rng.sample(jobs, k)]
    return out


# ----------------------------------------------------------------------------- systems


def make_tools(raw_mcp):
    from langchain_core.tools import tool

    class _Safe:  # a wrong argument comes back as an error result (like a real MCP server), not a crash
        async def call(self, agent, name, args):
            try:
                return await raw_mcp.call(agent, name, args)
            except Exception as exc:  # noqa: BLE001
                return {"error": f"{name} failed: {type(exc).__name__} {exc}"}

    mcp = _Safe()

    @tool
    async def get_job(job_id: str) -> dict:
        """Read a job post: title, description, skills, budget, client_id."""
        return await mcp.call("eval", "get_job", {"job_id": job_id})

    @tool
    async def get_client_history(client_id: str) -> dict:
        """Client history: rating, hire rate, jobs posted, total spent, payment verified."""
        return await mcp.call("eval", "get_client_history", {"client_id": client_id})

    @tool
    async def get_profile() -> dict:
        """The freelancer's profile: headline, skills, rate floors."""
        return await mcp.call("eval", "get_profile", {})

    @tool
    async def search_evidence(requirement: str, k: int = 3) -> dict:
        """Search the freelancer's portfolio for evidence for one requirement."""
        return await mcp.call(
            "eval", "search_evidence", {"requirement": requirement[:500], "k": min(k, 5)}
        )

    @tool
    async def get_market_rates(
        category: str, pay_type: str, skills: list[str] | None = None
    ) -> dict:
        """Market price band for a job category; pay_type is 'fixed' or 'hourly'."""
        return await mcp.call(
            "eval",
            "get_market_rates",
            {"category": category, "pay_type": pay_type, "skills": skills or []},
        )

    @tool
    async def verify_claims(draft: str) -> dict:
        """Check each claim in a draft letter against the portfolio evidence."""
        return await mcp.call("eval", "verify_claims", {"draft": draft[:6000]})

    return {
        t.name: t
        for t in (
            get_job,
            get_client_history,
            get_profile,
            search_evidence,
            get_market_rates,
            verify_claims,
        )
    }


def parse_final(text: str) -> dict:
    from agent.runtime import parse_json, strip_think

    try:
        d = parse_json(strip_think(text))
    except Exception:  # noqa: BLE001 - an unparseable answer counts as a skip with a parse error
        return {
            "decision": "skip",
            "is_scam": False,
            "price": None,
            "cover_letter": "",
            "parse_error": True,
        }
    return {"decision": "bid" if str(d.get("decision", "")).lower() == "bid" else "skip",
            "is_scam": bool(d.get("is_scam")), "price": _num(d.get("price")),
            "cover_letter": str(d.get("cover_letter") or ""), "parse_error": False}  # fmt: skip


def _num(x):
    try:
        return float(x) if x is not None else None
    except (TypeError, ValueError):
        return None


async def run_react(job: dict, model, mcp) -> dict:
    from langgraph.prebuilt import create_react_agent

    from agent.prompt_loader import render

    agent = create_react_agent(
        model, list(make_tools(mcp).values()), prompt=render("react_agent", job_id=job["job_id"])
    )
    out = await agent.ainvoke(
        {"messages": [("user", f"Handle job {job['job_id']}.")]}, {"recursion_limit": 30}
    )
    return parse_final(out["messages"][-1].content)


async def run_supervisor(job: dict, model, mcp) -> dict:
    from langgraph.prebuilt import create_react_agent
    from langgraph_supervisor import create_supervisor

    from agent.prompt_loader import render

    t = make_tools(mcp)
    roles = {"analyst": ["get_job", "get_client_history"], "researcher": ["get_profile", "search_evidence"],
             "writer": ["get_market_rates", "verify_claims"]}  # fmt: skip
    workers = [create_react_agent(model, [t[n] for n in names], name=role,
                                  prompt=render("sup_worker", role=role, job_id=job["job_id"]))
               for role, names in roles.items()]  # fmt: skip
    app = create_supervisor(
        workers, model=model, prompt=render("supervisor", job_id=job["job_id"])
    ).compile()
    out = await app.ainvoke(
        {"messages": [("user", f"Handle job {job['job_id']}.")]}, {"recursion_limit": 40}
    )
    return parse_final(out["messages"][-1].content)


async def run_graph(job: dict, model, mcp, _cache={}) -> dict:  # noqa: B006 - per-process graph cache
    from langgraph.checkpoint.memory import InMemorySaver

    from agent.graphs.bid_graph import build_bid_graph
    from agent.marketplace_port import load_config
    from agent.runtime import Deps

    if "g" not in _cache:
        _cache["cfg"] = load_config()
        _cache["g"] = build_bid_graph(_cache["cfg"], checkpointer=InMemorySaver())
    cfg, graph = _cache["cfg"], _cache["g"]
    deps = Deps(mcp=mcp, config=cfg, user=job["_persona"], llm=lambda node: model)
    tid = f"rdc:{job['job_id']}"
    out = await graph.ainvoke({"job_id": job["job_id"], "thread_id": tid, "user": job["_persona"]},
                              {"configurable": {"thread_id": tid}}, context=deps)  # fmt: skip
    d, risk = out.get("decision"), out.get("risk")
    letter = (
        out["__interrupt__"][0].value["draft"]["cover_letter"] if out.get("__interrupt__") else ""
    )
    return {"decision": "bid" if d and d.action == "bid" else "skip", "is_scam": bool(risk and risk.verdict == "block"),
            "price": out["price"].amount if out.get("price") else None, "cover_letter": letter, "parse_error": False,
            "compliance_blocked": out.get("status") == "blocked", "status": out.get("status")}  # fmt: skip


SYSTEMS = {"react": run_react, "supervisor": run_supervisor, "graph": run_graph}


# ----------------------------------------------------------------------------- scoring


async def run_system(name: str, jobs: list[dict], model, timeout_s: float) -> list[dict]:
    from langchain_core.callbacks import get_usage_metadata_callback

    from agent.nodes.proposal import check_compliance
    from agent.runtime import Deps
    from evals.inprocess_mcp import FakeMCP

    policy = Deps(mcp=None, config={}, user="").policy
    fakes = {p: FakeMCP(p) for p in PERSONAS}
    rows = []
    path = OUT / f"{name}.jobs.jsonl"
    path.write_text("", encoding="utf-8")
    for i, job in enumerate(jobs, 1):
        mcp = fakes[job["_persona"]]
        t0 = time.perf_counter()
        with get_usage_metadata_callback() as cb:
            try:
                res = await asyncio.wait_for(SYSTEMS[name](job, model, mcp), timeout_s)
                err = None
            except Exception as exc:  # noqa: BLE001 - record and continue
                res = {
                    "decision": "skip",
                    "is_scam": False,
                    "price": None,
                    "cover_letter": "",
                    "parse_error": False,
                }
                err = f"{type(exc).__name__}: {str(exc)[:200]}"
        latency = time.perf_counter() - t0
        tokens = sum(v.get("total_tokens", 0) for v in cb.usage_metadata.values())
        letter = res["cover_letter"].strip() if res["decision"] == "bid" else ""
        unsupported, claims = None, 0
        if letter:
            checks = (await mcp.call("eval", "verify_claims", {"draft": letter[:6000]}))["checks"]
            claims = len(checks)
            unsupported = (
                sum(c["status"] == "unsupported" for c in checks) / claims if claims else 0.0
            )
        violations = check_compliance(letter, policy, []).violations if letter else []
        g = job["_gold"]
        row = {"job_id": job["job_id"], "persona": job["_persona"], "gold_bid": g["bid"], "pred_bid": res["decision"],
               "gold_scam": g["is_scam"], "pred_scam": res["is_scam"], "gold_reason": g["skip_reason"], "pred_reason": None,
               "in_band": None if res["price"] is None or g["bid"] != "bid" else g["price_band"]["low"] <= res["price"] <= g["price_band"]["high"],
               "price": res["price"], "letter": letter, "claims": claims, "unsupported_rate": unsupported,
               "violations": violations, "compliance_blocked": res.get("compliance_blocked", False),
               "has_injection": bool(g.get("has_injection")), "parse_error": res.get("parse_error", False),
               "error": err, "tokens": tokens, "latency_s": round(latency, 2), "job": job}  # fmt: skip
        rows.append(row)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({k: v for k, v in row.items() if k != "job"}) + "\n")
        print(f"[{name}] {i}/{len(jobs)} {job['job_id']} gold={g['bid']} pred={res['decision']} "
              f"tok={tokens} {latency:.0f}s{' ERR ' + err if err else ''}", flush=True)  # fmt: skip
    return rows


def reply_rate(rows: list[dict]) -> tuple[float | None, int]:
    """Submit every letter the system would send to a fresh in-process GigSim; count answered."""
    from fastapi.testclient import TestClient
    from sqlalchemy import update

    from evals.metrics import mean
    from evals.runners.gigsim_outcomes import ADMIN, ANSWERED, TOKENS
    from gigsim import db
    from gigsim.app import create_app
    from gigsim.settings import Settings

    sent = [r for r in rows if r["letter"]]
    if not sent:
        return None, 0
    tmp = Path(tempfile.mkdtemp())
    settings = Settings(database_url=f"sqlite:///{(tmp / 'gs.db').as_posix()}", error_rate=0.0, time_scale=0.0,
                        include_heldout=False, rate_limit_per_min=1_000_000, release_interval_min=10_000)  # fmt: skip
    ids = []
    with TestClient(create_app(settings)) as c:
        with c.app.state.engine.begin() as conn:
            conn.execute(update(db.users).values(connects=10_000_000))
        for r in sent:
            j = r["job"]
            h = {"Authorization": f"Bearer {TOKENS[r['persona']]}"}
            bid = r["price"] or float(j.get("budget_usd") or j.get("hourly_low") or 30)
            p = c.post(
                "/proposals",
                headers=h,
                json={"job_id": j["job_id"], "cover_letter": r["letter"][:5000], "bid_amount": bid},
            ).json()
            if "proposal_id" not in p:
                continue
            c.post(
                f"/proposals/{p['proposal_id']}/submit",
                headers={**h, "Idempotency-Key": f"rdc:{j['job_id']}"},
            )
            ids.append(p["proposal_id"])
        c.post("/admin/tick", headers=ADMIN, params={"minutes": 60 * 24 * 30})
        decisions = {
            d["proposal_id"]: d for d in c.get("/admin/decisions", headers=ADMIN).json()["items"]
        }
    outcomes = [decisions[i]["outcome"] for i in ids if i in decisions]
    return (round(mean([float(o in ANSWERED) for o in outcomes]), 4) if outcomes else None), len(
        outcomes
    )


def summarize(name: str, rows: list[dict], model_desc: str) -> dict:
    from evals.metrics import mean
    from evals.runners.decision_eval import metrics
    from evals.runners.rag_eval import git_sha

    letters = [r for r in rows if r["letter"]]
    rr, n_sent = reply_rate(rows)
    lat = sorted(r["latency_s"] for r in rows)
    m = metrics(rows)
    m.pop("skip_reason_accuracy", None)  # only the graph reports skip reasons
    return {
        "runner": "evals/runners/multiagent_eval.py", "system": name, "model": model_desc, "split": "dev",
        "seed": SEED, "git_sha": git_sha(), "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "decisions": m,
        "letters": len(letters),
        "unsupported_claim_rate": round(mean([r["unsupported_rate"] for r in letters if r["unsupported_rate"] is not None]), 4) if letters else None,
        "letters_with_violations": sum(bool(r["violations"]) for r in letters),
        "compliance_blocks": sum(r["compliance_blocked"] for r in rows),
        "injection_jobs_bid_with_violation": sum(r["has_injection"] and bool(r["violations"]) for r in letters),
        "reply_rate": rr, "proposals_sent": n_sent,
        "tokens_per_job": round(mean([r["tokens"] for r in rows]), 1),
        "latency_mean_s": round(mean(lat), 2), "latency_p95_s": lat[min(len(lat) - 1, int(0.95 * len(lat)))],
        "errors": sum(bool(r["error"]) for r in rows), "parse_errors": sum(r["parse_error"] for r in rows),
    }  # fmt: skip


def write_summary() -> None:
    systems = {}
    for f in sorted(OUT.glob("*.json")):
        if f.name != "summary.json":
            d = json.loads(f.read_text(encoding="utf-8"))
            systems[d["system"]] = d
    (OUT / "summary.json").write_text(
        json.dumps({"runner": "evals/runners/multiagent_eval.py", "systems": systems}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--systems", nargs="+", choices=sorted(SYSTEMS), default=["graph", "react", "supervisor"]
    )
    ap.add_argument("--jobs", type=int, default=50)
    ap.add_argument("--provider", default="ollama")
    ap.add_argument("--model", default="llama3.2:3b")
    ap.add_argument("--timeout", type=float, default=600)
    a = ap.parse_args(argv)
    for role in (
        "STRONG",
        "SMALL",
        "FALLBACK_SMALL",
    ):  # one model for every role: a fair comparison
        os.environ[f"GIGBID_{role}_PROVIDER"] = a.provider
        os.environ[f"GIGBID_{role}_MODEL"] = a.model
    from agent.llm import chat_model

    model = chat_model("strong")
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = sample_jobs(a.jobs)

    async def all_systems():  # one event loop for every system (the model client is bound to it)
        return {name: await run_system(name, jobs, model, a.timeout) for name in a.systems}

    results = asyncio.run(all_systems())
    for name, rows in results.items():
        s = summarize(name, rows, f"{a.provider}:{a.model}")
        (OUT / f"{name}.json").write_text(json.dumps(s, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps(
                {
                    k: s[k]
                    for k in (
                        "system",
                        "letters",
                        "unsupported_claim_rate",
                        "reply_rate",
                        "tokens_per_job",
                        "latency_mean_s",
                    )
                }
            ),
            flush=True,
        )
        print(f"   decisions: {s['decisions']}", flush=True)
    write_summary()
    return 0


if __name__ == "__main__":
    sys.exit(main())
