"""One agent drafts one grounded proposal for a GigSim job - through MCP tools only.

Steps (all via GigBidMCPClient, allowlist `single_agent`):
  search_jobs -> get_job -> search_evidence per requirement -> LLM writes a cover letter that
  cites evidence ids -> citations checked against retrieved ids -> create_proposal_draft with
  dry_run=true (preview + Connects cost). It never submits.

Needs the MCP servers + GigSim running (`make up`). LLM: the `strong` role from agent/config.yaml,
or override, e.g. --provider ollama --model qwen2.5:3b. --offline skips the LLM and assembles
the letter from evidence with a template (to demo the tool flow without any model).

Usage:
  uv run python scripts/single_agent_proposal.py --persona ai_ml --query "chatbot internal PDFs"
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.llm import chat_model  # noqa: E402
from agent.mcp_client import GigBidMCPClient  # noqa: E402
from agent.prompt_loader import render  # noqa: E402

AGENT = "single_agent"
TOKENS = {
    "ai_ml": "dev-mcp-ai-ml",
    "fullstack": "dev-mcp-fullstack",
    "data_analyst": "dev-mcp-data-analyst",
}
CITE = re.compile(r"\[([a-z_]+:[a-z_]+:[A-Za-z0-9_\-]+)\]")


def requirements_of(job: dict) -> list[str]:
    bullets = [
        b.strip("-• ").strip()
        for b in job["description"].split("\n")
        if b.strip().startswith(("-", "•"))
    ]
    reqs = [b for b in bullets if len(b) > 6][:5]
    return reqs or (job.get("skills") or [])[:4] or [job["title"]]


def offline_letter(job: dict, evidence: list[dict]) -> str:
    cases = [e for e in evidence if e["type"] in {"case_study", "review", "readme"}][:2]
    lines = [f"You need help with {job['title'].lower()}."]
    lines += [f"{e['snippet'].rstrip('.')}. [{e['id']}]" for e in cases]
    lines.append("Happy to share a short plan for your project here on the platform.")
    return "\n\n".join(lines)


async def run(args) -> int:
    for noisy in ("httpx", "mcp", "mcp.client", "mcp.client.streamable_http"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    client = GigBidMCPClient(os.environ.get("GIGBID_MCP_TOKEN", TOKENS[args.persona]))
    print(f"trace_id: {client.trace_id}")

    if args.job_id:
        job_id = args.job_id
    else:
        page = await client.call(AGENT, "search_jobs", {"query": args.query, "limit": 5})
        if not page["items"]:
            print("no jobs found")
            return 1
        job_id = page["items"][0]["job_id"]
    job = await client.call(AGENT, "get_job", {"job_id": job_id})
    print(f"\nJOB {job['job_id']}: {job['title']}")

    evidence: dict[str, dict] = {}
    for req in requirements_of(job):
        hits = (await client.call(AGENT, "search_evidence", {"requirement": req, "k": 3}))["items"]
        print(f"  requirement: {req[:70]!r} -> {[h['id'] for h in hits]}")
        for h in hits:
            evidence.setdefault(h["id"], h)
    if not evidence:
        print("no supporting evidence found: an honest agent would skip this job")
        return 1

    ev_list = list(evidence.values())
    if args.offline:
        letter = offline_letter(job, ev_list)
    else:
        if args.provider:
            os.environ["GIGBID_STRONG_PROVIDER"] = args.provider
        if args.model:
            os.environ["GIGBID_STRONG_MODEL"] = args.model
        prompt = render(
            "single_agent_writer",
            job=f"{job['title']}\n\n{job['description']}",
            evidence="\n".join(f"- {e['id']}: {e['snippet']}" for e in ev_list),
        )
        letter = (await chat_model("strong").ainvoke(prompt)).content.strip()
        letter = re.sub(r"<think>.*?</think>", "", letter, flags=re.S).strip()  # reasoning models

    cited = set(CITE.findall(letter))
    unknown = sorted(cited - set(evidence))
    print("\n--- COVER LETTER ---\n" + letter + "\n--------------------")
    print(f"citations: {len(cited)} (unknown ids: {unknown or 'none'})")

    bid = job.get("budget_usd") or job.get("hourly_low") or 30
    preview = await client.call(
        AGENT,
        "create_proposal_draft",
        {
            "job_id": job["job_id"],
            "cover_letter": letter[:5000].ljust(50),
            "bid_amount": float(bid),
            "idempotency_key": f"single:{job['job_id']}:v1",
            "dry_run": True,
        },
    )
    print(
        f"dry run: would create a draft costing {preview['connects_cost']} Connects (nothing sent)"
    )
    return 0 if not unknown else 2


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--persona", choices=sorted(TOKENS), default="ai_ml")
    ap.add_argument("--query", default="chatbot internal PDFs")
    ap.add_argument("--job-id")
    ap.add_argument("--provider", help="override the strong model provider (ollama | groq)")
    ap.add_argument("--model", help="override the strong model name")
    ap.add_argument("--offline", action="store_true", help="no LLM: template letter from evidence")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
