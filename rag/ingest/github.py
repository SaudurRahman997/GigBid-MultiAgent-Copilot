"""Ingest the freelancer's REAL repositories through GitHub's official MCP server.

Uses langchain-mcp-adapters (Streamable HTTP) with a fine-grained, READ-ONLY personal access
token (GITHUB_PERSONAL_ACCESS_TOKEN) scoped to the repositories the user chose. Only this
ingestion job talks to GitHub; no agent node is given GitHub tools (see docs/TOOLS.md).
README and a few top-level source files per repo become Documents (type readme / code) with
the same metadata as local portfolio files, then go through the normal chunk -> index path.

    uv run python -m rag.ingest.github --persona fullstack owner/repo [owner/repo ...]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from langchain_mcp_adapters.client import MultiServerMCPClient

from rag.ingest.loaders import Document, detect_skills

GITHUB_MCP_URL = os.environ.get("GITHUB_MCP_URL", "https://api.githubcopilot.com/mcp/")
CODE_EXT = (".py", ".ts", ".tsx", ".js", ".sql", ".ipynb")
MAX_FILES = 4


def _text(result) -> str:
    if isinstance(result, list):
        return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in result)
    return str(result)


async def fetch_repo_docs(
    persona: str, repos: list[str], token: str | None = None
) -> list[Document]:
    token = token or os.environ.get("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_PERSONAL_ACCESS_TOKEN is not set (read-only, fine-grained)")
    client = MultiServerMCPClient(
        {
            "github": {
                "transport": "streamable_http",
                "url": GITHUB_MCP_URL,
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
    )
    tools = {t.name: t for t in await client.get_tools()}
    get_file = tools.get("get_file_contents")
    if get_file is None:
        raise RuntimeError(f"GitHub MCP server offers no get_file_contents tool: {sorted(tools)}")
    docs: list[Document] = []
    for full in repos:
        owner, repo = full.split("/", 1)
        readme = _text(await get_file.ainvoke({"owner": owner, "repo": repo, "path": "README.md"}))
        docs.append(
            Document(
                id=f"{persona}:readme:{repo}",
                persona=persona,
                type="readme",
                title=f"{repo} README",
                text=readme,
                source=f"github:{full}/README.md",
                skills=detect_skills(readme),
            )
        )
        listing = _text(await get_file.ainvoke({"owner": owner, "repo": repo, "path": "/"}))
        try:
            entries = json.loads(listing)
        except json.JSONDecodeError:
            entries = []
        files = [
            e["path"]
            for e in entries
            if isinstance(e, dict) and str(e.get("path", "")).endswith(CODE_EXT)
        ]
        for path in files[:MAX_FILES]:
            code = _text(await get_file.ainvoke({"owner": owner, "repo": repo, "path": path}))
            docs.append(
                Document(
                    id=f"{persona}:code:{repo}:{path}",
                    persona=persona,
                    type="code",
                    title=f"{repo}/{path}",
                    text=code[:20_000],
                    source=f"github:{full}/{path}",
                    skills=detect_skills(code),
                )
            )
    return docs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", required=True)
    ap.add_argument("repos", nargs="+", help="owner/repo")
    args = ap.parse_args(argv)
    docs = asyncio.run(fetch_repo_docs(args.persona, args.repos))
    for d in docs:
        print(d.id, len(d.text), "chars", d.skills[:5])
    return 0


if __name__ == "__main__":
    sys.exit(main())
