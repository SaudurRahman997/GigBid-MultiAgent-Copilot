"""R&D A - tool granularity: fine-grained tools vs coarse tools vs fine tools with rewritten descriptions.

40 tasks with a known correct call (generated from the dev data, seeded). Each task is one
tool-calling turn of the same model with one of three tool sets:
  fine    the 18 MCP tools exactly as the servers publish them (tests/contract/snapshots/*.json)
  coarse  3 tools, one per server: {action: <tool name>, args: {...}}
  best    the 18 tools with rewritten descriptions (when to use it, when not, argument formats)
Metrics: tool-selection accuracy (right tool / right server+action), argument accuracy (every gold
argument present and correct, among correctly selected calls and overall), tokens per task.

Writes evals/results/tools/granularity.json (+ granularity.jobs.jsonl).
Usage: uv run python -m evals.runners.tool_granularity [--provider ollama --model llama3.2:3b]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "evals" / "results" / "tools"
SEED = 20261115
SERVERS = ("portfolio", "marketplace", "workspace")
SYSTEM = "You are a freelancer's assistant. Answer the request by calling exactly one tool. Do not ask questions."

BEST = {  # rewritten descriptions: purpose, when to use, when not, argument formats
    "get_case_study": "Return the FULL text of one portfolio case study. Use when the user names a case-study id like 'ai_ml:case:03'. Argument id = that exact id.",
    "get_profile": "Return the freelancer's own profile: headline, skills, MINIMUM hourly rate and fixed budget (floors), target rate. Use for questions about the freelancer's own rates or headline, not market prices.",
    "list_skills": "List every skill the freelancer's portfolio proves, with evidence counts. Use for 'which skills can I back up?'. Not for searching one requirement.",
    "search_evidence": "Search the freelancer's portfolio for proof of ONE requirement (e.g. 'RAG chatbot', 'React dashboards'). Use to find evidence for a claim or job requirement. Argument requirement = the requirement in plain words.",
    "verify_claims": "Check a DRAFT letter's factual claims against the portfolio (supported / unsupported). Use when the user gives draft text to check. Argument draft = the full draft text.",
    "create_proposal_draft": "Create a DRAFT proposal for a job (not sent, costs nothing). Use dry_run=true to only preview. Arguments: job_id like 'gj_1234abcd', bid_amount in USD, cover_letter text, idempotency_key.",
    "get_client_history": "Return a CLIENT's public track record (rating, hire rate, spend, payment verified). Use for 'is client cl_0123 reliable?'. Argument client_id like 'cl_0123'.",
    "get_connects_balance": "Return how many Connects (bid credits) the freelancer has left. No arguments.",
    "get_job": "Return the FULL post of ONE job by id. Use when the user names a job id like 'gj_1234abcd'. Argument job_id = that id. Not for searching.",
    "get_market_rates": "Return the market price band (p25-p75) for a job category and pay type. Use for 'what do <category> <fixed|hourly> jobs pay?'. Arguments: category (ai_ml | fullstack | data_analyst | other), pay_type (fixed | hourly).",
    "list_messages": "Without thread_id: list the freelancer's message threads. With thread_id (like 'th_0123'): return that conversation's messages. Use to read client conversations.",
    "search_jobs": "Search OPEN jobs by keywords and optional category. Use for 'find jobs about X'. Argument query = the keywords. Not for one known job id (use get_job).",
    "send_message": "Send a message to a client in an existing thread. Only after human approval. Arguments: thread_id, text, idempotency_key.",
    "submit_proposal": "Send an existing draft proposal to the client and SPEND Connects. Irreversible; only after human approval. Arguments: proposal_id, idempotency_key.",
    "create_email_draft": "Save an email draft for the freelancer's own review (never sends; not for marketplace clients). Arguments: to, subject, body, idempotency_key.",
    "create_tentative_hold": "Reserve a calendar slot tentatively (e.g. an interview). Arguments: start (ISO time like 2026-11-20T10:00:00Z), duration_min (minutes), title, idempotency_key.",
    "free_slots": "List the freelancer's FREE calendar slots between two times (max 14 days). Arguments: start and end as ISO times like 2026-11-20T09:00:00Z, optional duration_min.",
}  # fmt: skip


def snapshot_tools() -> dict[str, list[dict]]:
    out = {}
    for s in SERVERS:
        d = json.loads(
            (ROOT / "tests" / "contract" / "snapshots" / f"{s}.json").read_text(encoding="utf-8")
        )
        out[s] = [
            {"name": t["name"], "description": t["description"], "parameters": t["inputSchema"]}
            for t in d["tools"]
        ]
    return out


def toolsets() -> dict[str, list[dict]]:
    snap = snapshot_tools()
    fine = [t for s in SERVERS for t in snap[s]]
    best = [{**t, "description": BEST.get(t["name"], t["description"])} for t in fine]
    coarse = []
    for s in SERVERS:
        actions = [t["name"] for t in snap[s]]
        lines = "; ".join(
            f"{t['name']}({', '.join(t['parameters']['properties'])}): {t['description'].split('.')[0]}"
            for t in snap[s]
        )
        coarse.append({"name": s, "description": f"{s.capitalize()} server. Pick an action and pass its arguments in args. Actions: {lines}.",
                       "parameters": {"type": "object", "required": ["action", "args"], "properties": {
                           "action": {"type": "string", "enum": actions}, "args": {"type": "object", "description": "Arguments of the chosen action"}}}})  # fmt: skip
    return {"fine": fine, "coarse": coarse, "best": best}


def server_of(tool: str) -> str:
    snap = snapshot_tools()
    return next(s for s in SERVERS if any(t["name"] == tool for t in snap[s]))


def tasks(n: int = 40) -> list[dict]:
    """Seeded tasks from the dev data. gold: tool, args to check (exact) and args_contains (substring)."""
    from evals.runners.rag_eval import read_jobs

    r = random.Random(SEED)
    jobs = [j for p in ("ai_ml", "fullstack", "data_analyst") for j in read_jobs("dev", p)]
    cases = [json.loads(x)["id"] for x in (ROOT / "data/personas/ai_ml/evidence.jsonl").read_text(encoding="utf-8").splitlines()
             if x and ":case:" in json.loads(x)["id"]]  # fmt: skip
    threads = [
        json.loads(x)["thread_id"]
        for x in (ROOT / "data/synthetic/conversations.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if x
    ]
    skills = [
        "RAG chatbots",
        "React dashboards",
        "churn prediction",
        "Power BI reports",
        "Django REST APIs",
        "invoice OCR",
    ]
    T = [
        lambda: (f"Open the full post for job {(j := r.choice(jobs))['job_id']}.", "get_job", {"job_id": j["job_id"]}, {}),
        lambda: (f"Is client {(c := r.choice(jobs)['client_id'])} reliable? Check their track record.", "get_client_history", {"client_id": c}, {}),
        lambda: (f"Find proof in my portfolio that I have done {(s := r.choice(skills))}.", "search_evidence", {}, {"requirement": s.split()[0]}),
        lambda: (f"What do {(cat := r.choice(['ai_ml', 'fullstack', 'data_analyst']))} {(pt := r.choice(['fixed', 'hourly']))}-price jobs usually pay?", "get_market_rates", {"category": cat, "pay_type": pt}, {}),
        lambda: ("How many Connects do I have left?", "get_connects_balance", {}, {}),
        lambda: ("What minimum hourly rate did I set for myself?", "get_profile", {}, {}),
        lambda: ("Which skills can my portfolio actually back up?", "list_skills", {}, {}),
        lambda: (f"Show me the full case study {(cid := r.choice(cases))}.", "get_case_study", {"id": cid}, {}),
        lambda: ("Check whether this draft overclaims: 'I have built 40 production RAG systems and cut support costs by 90%.'", "verify_claims", {}, {"draft": "RAG"}),
        lambda: (f"Look for open jobs about {(s := r.choice(skills))}.", "search_jobs", {}, {"query": s.split()[0]}),
        lambda: (f"Read the conversation in thread {(t := r.choice(threads))}.", "list_messages", {"thread_id": t}, {}),
        lambda: ("When am I free between 2026-11-20T09:00:00Z and 2026-11-22T17:00:00Z?", "free_slots", {"start": "2026-11-20T09:00:00Z", "end": "2026-11-22T17:00:00Z"}, {}),
        lambda: ("Pencil in a 30-minute interview at 2026-11-21T10:00:00Z titled 'Client interview'.", "create_tentative_hold", {"start": "2026-11-21T10:00:00Z", "duration_min": 30}, {}),
        lambda: (f"Preview, as a dry run only, a $400 proposal for job {(j := r.choice(jobs))['job_id']}.", "create_proposal_draft", {"job_id": j["job_id"], "bid_amount": 400, "dry_run": True}, {}),
    ]  # fmt: skip
    out = []
    for i in range(n):
        text, tool, exact, contains = T[i % len(T)]()
        out.append(
            {
                "id": f"t{i + 1:02d}",
                "task": text,
                "tool": tool,
                "args": exact,
                "args_contains": contains,
            }
        )
    return out


def score(task: dict, toolset: str, call: dict | None) -> dict:
    if not call:
        return {"selected": False, "args_ok": False, "called": None}
    name, args = call["name"], call.get("args") or {}
    if toolset == "coarse":
        sel = name == server_of(task["tool"]) and args.get("action") == task["tool"]
        args = args.get("args") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = {}
    else:
        sel = name == task["tool"]
    ok = (
        sel
        and all(_eq(args.get(k), v) for k, v in task["args"].items())
        and all(v.lower() in str(args.get(k, "")).lower() for k, v in task["args_contains"].items())
    )
    return {"selected": sel, "args_ok": ok, "called": {"name": name, "args": args}}


def _eq(got, want) -> bool:
    if isinstance(want, bool):
        return got is True or str(got).lower() == "true" if want else got in (False, None, "false")
    if isinstance(want, int | float):
        try:
            return float(got) == float(want)
        except (TypeError, ValueError):
            return False
    return str(got).strip() == str(want)


async def run(model, sets: dict, ts: list[dict]) -> list[dict]:
    rows = []
    for name, tools in sets.items():
        bound = model.bind_tools([{"type": "function", "function": t} for t in tools])
        for t in ts:
            msg = await bound.ainvoke([("system", SYSTEM), ("user", t["task"])])
            call = msg.tool_calls[0] if getattr(msg, "tool_calls", None) else None
            um = getattr(msg, "usage_metadata", None) or {}
            rows.append(
                {
                    "toolset": name,
                    "task_id": t["id"],
                    "gold_tool": t["tool"],
                    "tokens": um.get("total_tokens", 0),
                    **score(t, name, call),
                }
            )
            print(
                f"[{name}] {t['id']} gold={t['tool']} got={call['name'] if call else None} ok={rows[-1]['args_ok']}",
                flush=True,
            )
    return rows


def main(argv: list[str] | None = None) -> int:
    from evals.runners.rag_eval import git_sha

    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="ollama")
    ap.add_argument("--model", default="llama3.2:3b")
    a = ap.parse_args(argv)
    os.environ["GIGBID_STRONG_PROVIDER"], os.environ["GIGBID_STRONG_MODEL"] = a.provider, a.model
    from agent.llm import chat_model

    sets, ts = toolsets(), tasks()
    rows = asyncio.run(run(chat_model("strong"), sets, ts))
    summary = {"runner": "evals/runners/tool_granularity.py", "git_sha": git_sha(), "seed": SEED, "model": f"{a.provider}:{a.model}",
               "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "tasks": len(ts),
               "tools_per_set": {k: len(v) for k, v in sets.items()}, "toolsets": {}}  # fmt: skip
    for name in sets:
        rs = [r for r in rows if r["toolset"] == name]
        sel = [r for r in rs if r["selected"]]
        summary["toolsets"][name] = {
            "tool_selection_accuracy": round(len(sel) / len(rs), 4),
            "argument_accuracy": round(sum(r["args_ok"] for r in rs) / len(rs), 4),
            "argument_accuracy_given_right_tool": round(sum(r["args_ok"] for r in sel) / len(sel), 4) if sel else None,
            "no_tool_call": sum(r["called"] is None for r in rs),
            "tokens_per_task": round(sum(r["tokens"] for r in rs) / len(rs), 1),
        }  # fmt: skip
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "granularity.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    with (OUT / "granularity.jobs.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(json.dumps(summary["toolsets"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
