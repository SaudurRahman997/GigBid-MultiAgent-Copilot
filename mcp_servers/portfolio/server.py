"""Portfolio MCP server (read-only): the freelancer's evidence, retrieved for agents.

Tools      search_evidence(requirement, k, filters), get_case_study(id), list_skills()
Resources  portfolio://case/{id}, portfolio://proposal/{id}, portfolio://repo/{name}
Prompts    answer_screening_question, summarise_experience, cover_letter_opening
Retrieval  rag/retriever.py with the variant from agent/config.yaml (rag.variant).
Each caller only sees the persona mapped to their bearer token.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Annotated

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ResourceError, ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from mcp_servers.common.runtime import (
    TokenBucket,
    ToolRunner,
    current_user,
    make_server,
    tenant_id,
)
from mcp_servers.common.settings import MCPSettings
from mcp_servers.common.store import Store
from rag import uploads
from rag.corpus import Document, load_corpus
from rag.retriever import EvidenceFilters, retriever_for

SERVER = "portfolio"
PORT = 8201
PROMPTS = Path(__file__).with_name("prompts")
INSTRUCTIONS = (
    "Read-only access to the freelancer's portfolio: case studies, client reviews, repo "
    "READMEs, code samples, CV and past proposals with outcomes. Cite evidence ids for claims."
)
READ = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False
)
Requirement = Annotated[
    str,
    Field(min_length=3, max_length=500, description="One job requirement, in the client's words"),
]


class EvidenceItem(BaseModel):
    id: str
    type: str
    title: str
    source: str = Field(description="File inside the persona's portfolio")
    date: str | None = None
    outcome: str | None = Field(None, description="e.g. 'rated 5.0/5; rehired', '4.8/5', 'won'")
    project_id: str | None = None
    snippet: str
    score: float


class EvidenceSearchResult(BaseModel):
    variant: str = Field(description="Retrieval variant that produced the ranking")
    items: list[EvidenceItem]


class CaseStudy(BaseModel):
    id: str
    title: str
    date: str | None
    client_industry: str | None
    outcome: str | None
    project_id: str | None
    skills: list[str]
    text: str


class SkillCount(BaseModel):
    skill: str
    evidence_count: int


class SkillsResult(BaseModel):
    persona: str
    skills: list[SkillCount]


class Profile(BaseModel):
    persona: str
    name: str
    headline: str
    category: str
    skills: list[str]
    floors: dict[str, float] = Field(description="minimum acceptable fixed budget and hourly rate")
    target_rate: float


class ClaimCheckOut(BaseModel):
    text: str
    status: str
    evidence: list[str]
    cited: list[str]
    reason: str


class VerifyResult(BaseModel):
    checks: list[ClaimCheckOut]
    unsupported_rate: float
    judge: str


class NotFoundError(LookupError):
    code = "not_found"


def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.v1.md").read_text(encoding="utf-8").split("---", 2)[-1].strip()


def build_server(settings: MCPSettings | None = None, store: Store | None = None) -> FastMCP:
    s = settings or MCPSettings()
    db = store or Store(s.database_url)
    runner = ToolRunner(SERVER, s, db, TokenBucket(s.rate_limit_per_min))
    mcp = make_server("gigbid-portfolio", INSTRUCTIONS, s, PORT)
    data_dir = str(s.data_dir)

    def corpus(user: str, tenant: str | None = None) -> tuple[Document, ...]:
        persona = s.persona_for(user)
        docs = load_corpus(persona, data_dir)
        if not docs:
            raise ToolError(f"not_found: no portfolio for user {user!r}")
        return (*docs, *uploads.documents(persona, tenant, Document))

    def find(user: str, doc_id: str, types: set[str], tenant: str | None = None) -> Document:
        doc = next((d for d in corpus(user, tenant) if d.id == doc_id and d.type in types), None)
        if doc is None:
            raise NotFoundError(f"{doc_id} not found in your portfolio")
        return doc

    def item(h) -> EvidenceItem:
        d = h.doc
        return EvidenceItem(
            id=d.id,
            type=d.type,
            title=d.title,
            source=d.source,
            date=d.date,
            outcome=d.outcome,
            project_id=d.project_id,
            snippet=h.snippet,
            score=h.score,
        )

    @mcp.tool(annotations=READ, title="Search portfolio evidence")
    async def search_evidence(
        requirement: Requirement,
        k: Annotated[int, Field(ge=1, le=20)] = 5,
        filters: EvidenceFilters | None = None,
        ctx: Context | None = None,
    ) -> EvidenceSearchResult:
        """Find portfolio evidence (case studies, reviews, READMEs, code, CV, past proposals)
        that supports ONE requirement. Query once per requirement for best results."""

        async def fn(user: str) -> EvidenceSearchResult:
            r = retriever_for(s.persona_for(user), tenant_id(ctx), None, data_dir)
            hits = r.search(requirement, k, filters)
            return EvidenceSearchResult(variant=r.variant, items=[item(h) for h in hits])

        args = {
            "requirement": requirement,
            "k": k,
            "filters": filters.model_dump() if filters else None,
        }
        return await runner.run(
            "search_evidence", args, ctx, fn, lambda r: f"{len(r.items)} hits ({r.variant})"
        )

    @mcp.tool(annotations=READ, title="Get case study")
    async def get_case_study(
        id: Annotated[
            str, Field(min_length=3, max_length=80, description="Evidence id, e.g. ai_ml:case:03")
        ],
        ctx: Context | None = None,
    ) -> CaseStudy:
        """Full text and metadata of one case study."""

        async def fn(user: str) -> CaseStudy:
            d = find(user, id, {"case_study"}, tenant_id(ctx))
            return CaseStudy(
                id=d.id,
                title=d.title,
                date=d.date,
                client_industry=d.client_industry,
                outcome=d.outcome,
                project_id=d.project_id,
                skills=list(d.skills),
                text=d.text,
            )

        return await runner.run("get_case_study", {"id": id}, ctx, fn, lambda r: r.id)

    @mcp.tool(annotations=READ, title="List skills")
    async def list_skills(ctx: Context | None = None) -> SkillsResult:
        """Skills evidenced in the portfolio, with how many evidence items support each."""

        async def fn(user: str) -> SkillsResult:
            docs = corpus(user, tenant_id(ctx))
            counts = Counter(sk for d in docs if d.type != "proposal" for sk in d.skills)
            ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
            return SkillsResult(
                persona=s.persona_for(user),
                skills=[SkillCount(skill=name, evidence_count=n) for name, n in ranked],
            )

        return await runner.run("list_skills", {}, ctx, fn, lambda r: f"{len(r.skills)} skills")

    @mcp.tool(annotations=READ, title="Get freelancer profile")
    async def get_profile(ctx: Context | None = None) -> Profile:
        """The freelancer's profile: headline, evidenced skills, minimum budget/rate, target rate."""

        async def fn(user: str) -> Profile:
            import json as _json

            path = s.data_dir / "personas" / s.persona_for(user) / "profile.json"
            if not path.exists():
                raise NotFoundError(f"no profile for user {user!r}")
            p = _json.loads(path.read_text(encoding="utf-8"))
            return Profile(
                persona=p["persona"],
                name=p["name"],
                headline=p["headline"],
                category=p["category"],
                skills=p["skills"],
                floors=p["floors"],
                target_rate=p["target_rate"],
            )

        return await runner.run("get_profile", {}, ctx, fn, lambda r: r.persona)

    @mcp.tool(annotations=READ, title="Verify claims in a draft")
    async def verify_claims(
        draft: Annotated[
            str, Field(min_length=20, max_length=6000, description="Proposal or message text")
        ],
        ctx: Context | None = None,
    ) -> VerifyResult:
        """Split a draft into factual claims and check each against the portfolio:
        supported | partial | unsupported, with the evidence ids that back it."""

        async def fn(user: str) -> VerifyResult:
            from rag.verify import config as verify_config
            from rag.verify import default_judge, unsupported_rate, verify

            cfg = verify_config()
            retriever = retriever_for(
                s.persona_for(user), tenant_id(ctx), cfg["retrieval_variant"], data_dir
            )
            judge = default_judge()
            checks = verify(draft, retriever, judge, cfg["k"])
            return VerifyResult(
                checks=[
                    ClaimCheckOut(
                        text=c.text,
                        status=c.status,
                        evidence=c.evidence,
                        cited=c.cited,
                        reason=c.reason,
                    )
                    for c in checks
                ],
                unsupported_rate=round(unsupported_rate(checks), 4),
                judge=judge.name,
            )

        return await runner.run(
            "verify_claims",
            {"draft": draft},
            ctx,
            fn,
            lambda r: f"{len(r.checks)} claims, unsupported {r.unsupported_rate}",
        )

    # ------------------------------------------------------------------ resources
    def resource_doc(doc_id: str, types: set[str]) -> Document:
        try:
            return find(current_user(s), doc_id, types)
        except NotFoundError as exc:
            raise ResourceError(str(exc)) from exc

    @mcp.resource(
        "portfolio://case/{id}",
        name="case_study",
        mime_type="text/markdown",
        description="A case study by evidence id (e.g. ai_ml:case:03)",
    )
    def case_resource(id: str) -> str:
        return resource_doc(id, {"case_study"}).text

    @mcp.resource(
        "portfolio://proposal/{id}",
        name="past_proposal",
        mime_type="text/plain",
        description="A past proposal by id, with its outcome",
    )
    def proposal_resource(id: str) -> str:
        d = resource_doc(id, {"proposal"})
        return f"Outcome: {d.outcome}\nJob: {d.title}\n\n{d.text}"

    @mcp.resource(
        "portfolio://repo/{name}",
        name="repo_readme",
        mime_type="text/markdown",
        description="README of a portfolio repository by name",
    )
    def repo_resource(name: str) -> str:
        pid = s.persona_for(current_user(s))
        return resource_doc(f"{pid}:readme:{name}", {"readme"}).text

    # ------------------------------------------------------------------ prompts
    @mcp.prompt(title="Answer a screening question from my portfolio")
    def answer_screening_question(question: str) -> str:
        return _prompt("answer_screening_question").replace("{question}", question)

    @mcp.prompt(title="Summarise my experience with a skill")
    def summarise_experience(skill: str) -> str:
        return _prompt("summarise_experience").replace("{skill}", skill)

    @mcp.prompt(title="Draft a cover letter opening for a job")
    def cover_letter_opening(job: str) -> str:
        return _prompt("cover_letter_opening").replace("{job}", job)

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request):  # pragma: no cover - exercised in docker
        from starlette.responses import JSONResponse

        return JSONResponse({"status": "ok", "server": SERVER})

    mcp.store = db  # type: ignore[attr-defined]
    return mcp
