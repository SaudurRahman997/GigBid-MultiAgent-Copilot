"""Generate the three synthetic freelancer portfolios (data/personas/<persona>/).

Per persona: 15-25 projects drawn from the archetypes in persona_specs.yaml, each described
several ways (case study, client review, CV bullet, sometimes a repo README + code sample).
The corpus is deliberately hard for naive RAG:
  * the same project is told three or more ways with different vocabulary;
  * case studies often IMPLY skills ("grounds answers in the client's own documents") instead of
    naming them; READMEs name the stack explicitly; reviews talk outcomes, not tech;
  * archetypes repeat across industries, so near-duplicate projects compete in retrieval;
  * code and prose are mixed in the same corpus.

Outputs per persona:
  profile.json, cv.md, cv.pdf, case_studies/*.md, repos/<name>/{README.md, code},
  reviews.jsonl, evidence.jsonl (index of every evidence item), _meta/projects.json
  (generator-side facts used to build gold labels; not for ingestion).
"""

from __future__ import annotations

import random
from datetime import timedelta
from pathlib import Path

from fpdf import FPDF

from data.generators.common import (
    PERSONAS,
    REF_NOW,
    front_matter,
    iso,
    provenance,
    rng,
    slug,
    specs,
    stamp,
    write_json,
    write_jsonl,
    write_text,
)

PROV = provenance(__file__)
MIN_PROJECTS, MAX_PROJECTS = 17, 23
MAX_PER_ARCHETYPE = 3
MIN_REPOS, MAX_REPOS = 5, 8
REVIEWER_ROLES = ["Founder", "Operations Manager", "Head of Product", "CTO", "Marketing Lead",
                  "Finance Director", "Practice Manager", "COO", "Engineering Manager"]  # fmt: skip


# ----------------------------------------------------------------------------- projects


def _numbers(r: random.Random) -> dict:
    a = r.choice([3, 4, 5, 6, 8, 12, 15, 20, 40, 120, 300, 1200, 4000])
    return {"a": a, "b": r.choice([2, 3, 5, 10, 15, 30]), "p": r.randint(12, 68)}


def build_projects(pid: str, persona: dict, r: random.Random) -> list[dict]:
    archetypes = persona["archetypes"]
    n = r.randint(MIN_PROJECTS, MAX_PROJECTS)
    order = [a["key"] for a in archetypes]  # every archetype at least once
    counts = dict.fromkeys(order, 1)
    while len(order) < n:
        key = r.choice([k for k, c in counts.items() if c < MAX_PER_ARCHETYPE])
        counts[key] += 1
        order.append(key)
    r.shuffle(order)
    by_key = {a["key"]: a for a in archetypes}
    industries = specs()["industries"]
    used: dict[str, set[str]] = {}
    projects = []
    for i, key in enumerate(order, start=1):
        arch = by_key[key]
        free = [k for k in sorted(industries) if k not in used.setdefault(key, set())]
        ind = r.choice(free)
        used[key].add(ind)
        start = REF_NOW - timedelta(days=r.randint(60, 5 * 365))
        weeks = r.randint(3, 20)
        nums = _numbers(r)
        rating = r.choices([5.0, 4.9, 4.8, 4.6, 4.3], weights=[55, 15, 12, 10, 8])[0]
        projects.append(
            {
                "project_id": f"{pid}:p{i:02d}",
                "persona": pid,
                "archetype": key,
                "industry": ind,
                "industry_noun": industries[ind]["noun"],
                "client": r.choice(industries[ind]["names"]),
                "title": title_for(arch["title"], industries[ind]["noun"]),
                "start": iso(start),
                "end": iso(start + timedelta(weeks=weeks)),
                "weeks": weeks,
                "skills": list(arch["skills"]),
                "metric": r.choice(arch["metrics"]).format(**nums),
                "numbers": nums,
                "rating": rating,
                "rehired": r.random() < 0.35,
            }
        )
    projects.sort(key=lambda p: p["start"])
    for i, p in enumerate(projects, start=1):  # ids in chronological order
        p["project_id"] = f"{pid}:p{i:02d}"
    return projects


def with_article(noun: str) -> str:
    return ("an " if noun[0].lower() in "aeiou" else "a ") + noun


def title_for(template: str, noun: str) -> str:
    return (
        template.replace("an {noun}", "{x}").replace("a {noun}", "{x}").format(x=with_article(noun))
    )


def _fill(text: str, p: dict) -> str:
    return text.format(client=p["client"], noun=p["industry_noun"], **p["numbers"])


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


# ----------------------------------------------------------------------------- case studies


def case_study(p: dict, arch: dict, r: random.Random) -> tuple[str, list[str]]:
    """Markdown body + skills named explicitly in it (others are only implied)."""
    problem = _cap(_fill(arch["problem"], p))
    steps = [_fill(s, p) for s in arch["approach"]]
    style = r.choice(["story", "bullets", "star"])
    show_stack = r.random() < 0.45  # often the stack is NOT listed -> skills only implied
    named = list(p["skills"]) if show_stack else []
    stack = f"\n\n**Stack:** {', '.join(p['skills'])}" if show_stack else ""
    when = p["start"][:7]
    if style == "story":
        body = (
            f"# {p['title']}\n\n_{p['client']} · {p['industry_noun']} · {when} · "
            f"{p['weeks']} weeks_\n\n{problem}. I {steps[0]}. Along the way I {steps[1]}, and "
            f"finally {steps[2]}.\n\nThe result: we {p['metric']}.{stack}"
        )
    elif style == "bullets":
        lines = "\n".join(f"- {_cap(s)}" for s in steps)
        body = (
            f"# {p['title']}\n\n**Client:** {p['client']} ({p['industry_noun']})  \n"
            f"**When:** {when}, {p['weeks']} weeks\n\n## Challenge\n{problem}.\n\n"
            f"## What I did\n{lines}\n\n## Outcome\n{_cap(p['metric'])}.{stack}"
        )
    else:
        body = (
            f"# {p['title']}\n\n**Situation.** {problem}.\n\n**Task.** {p['client']} needed "
            f"this fixed within {p['weeks']} weeks.\n\n**Action.** {_cap(steps[0])}; "
            f"{steps[1]}; {steps[2]}.\n\n**Result.** {_cap(p['metric'])}.{stack}"
        )
    return body, named


# ----------------------------------------------------------------------------- reviews

REVIEW_OPENERS = [
    "{name} understood our problem faster than we did.",
    "Working with {name} was easy from day one.",
    "We have hired many freelancers; {name} is one of the few we rehired.",
    "Clear communication, honest estimates and great work.",
    "{name} took a messy brief and turned it into something our team uses daily.",
    "Exactly what we needed, delivered on time.",
]
REVIEW_MIDDLES = [
    "Before this, {problem_lc}. Now we {metric}.",
    "The headline number: we {metric}.",
    "{problem}. That is no longer the case - we {metric}.",
    "Within a few weeks we {metric}.",
]
REVIEW_CLOSERS = [
    "Highly recommended.",
    "Would hire again without hesitation.",
    "Already planning the next project together.",
    "Great to work with.",
    "",
]


def review(p: dict, arch: dict, persona: dict, r: random.Random, nth: int) -> dict:
    first = persona["name"].split()[0]
    problem = _cap(_fill(arch["problem"], p))
    text = " ".join(
        s
        for s in (
            r.choice(
                REVIEW_OPENERS if p["rehired"] else REVIEW_OPENERS[:2] + REVIEW_OPENERS[3:]
            ).format(name=first),
            r.choice(REVIEW_MIDDLES).format(
                problem=problem, problem_lc=problem[0].lower() + problem[1:], metric=p["metric"]
            ),
            r.choice(REVIEW_CLOSERS),
        )
        if s
    )
    rating = p["rating"] if nth == 0 else max(4.0, round(p["rating"] - r.choice([0, 0.1, 0.3]), 1))
    return {
        "reviewer": f"{r.choice(REVIEWER_ROLES)}, {p['client']}",
        "rating": rating,
        "text": text,
        "date": p["end"],
    }


# ----------------------------------------------------------------------------- repos + code

CODE = {
    "fastapi_rag": (
        "app.py",
        """from fastapi import FastAPI
from pydantic import BaseModel

from retrieval import search, rerank
from llm import answer_with_citations

app = FastAPI(title="{repo}")


class Question(BaseModel):
    text: str
    k: int = 5


@app.post("/ask")
def ask(q: Question) -> dict:
    hits = rerank(q.text, search(q.text, k=q.k * 4))[: q.k]
    return answer_with_citations(q.text, hits)  # every sentence cites a chunk id
""",
    ),
    "sklearn_model": (
        "train.py",
        """import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import TimeSeriesSplit, cross_val_score

features = pd.read_parquet("features.parquet")
X, y = features.drop(columns=["churned_30d"]), features["churned_30d"]
model = CalibratedClassifierCV(HistGradientBoostingClassifier(max_depth=6), cv=3)
print("AUC", cross_val_score(model, X, y, cv=TimeSeriesSplit(5), scoring="roc_auc").mean())
model.fit(X, y)
""",
    ),
    "tool_agent": (
        "agent.py",
        '''TOOLS = [calendar.free_slots, calendar.hold_slot, crm.lookup_contact]


def run(request: str, approve) -> str:
    """Plan with tool calls; anything that leaves the system needs human approval."""
    plan = llm.plan(request, tools=TOOLS)
    for call in plan.calls:
        if call.sends_external and not approve(call):
            return "Waiting for approval"
        audit.log(call.name, call.args, call.run())
    return plan.summary
''',
    ),
    "vision_model": (
        "infer.py",
        """import cv2
import torch

model = torch.jit.load("defects.pt").eval()


def inspect(path: str) -> dict:
    img = cv2.imread(path)
    img = cv2.createCLAHE(clipLimit=2.0).apply(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    with torch.no_grad():
        score = model(torch.from_numpy(img).float()[None, None] / 255).sigmoid().item()
    return {"defect": score > 0.5, "score": round(score, 3)}
""",
    ),
    "python_util": (
        "evaluate.py",
        """import json
from statistics import mean


def recall_at_k(gold: set[str], ranked: list[str], k: int = 5) -> float:
    return len(gold & set(ranked[:k])) / max(len(gold), 1)


rows = [json.loads(line) for line in open("runs.jsonl")]
print("Recall@5", round(mean(recall_at_k(set(r["gold"]), r["ranked"]) for r in rows), 3))
""",
    ),
    "react_component": (
        "UsageChart.tsx",
        """import { useMemo, useState } from "react";

type Point = { day: string; events: number; account: string };

export function UsageChart({ data }: { data: Point[] }) {
  const [account, setAccount] = useState<string>("all");
  const rows = useMemo(
    () => data.filter((d) => account === "all" || d.account === account),
    [data, account],
  );
  return (
    <section aria-label="Usage">
      <select value={account} onChange={(e) => setAccount(e.target.value)}>
        <option value="all">All accounts</option>
      </select>
      <Bars rows={rows} />
    </section>
  );
}
""",
    ),
    "next_api_route": (
        "route.ts",
        """import { NextResponse } from "next/server";
import { db } from "@/lib/db";

export async function POST(req: Request) {
  const { slotId, email } = await req.json();
  const booking = await db.$transaction(async (tx) => {
    const slot = await tx.slot.findUniqueOrThrow({ where: { id: slotId } });
    if (slot.bookedAt) throw new Error("Slot already taken");
    return tx.booking.create({ data: { slotId, email } });
  });
  return NextResponse.json(booking, { status: 201 });
}
""",
    ),
    "express_route": (
        "jobs.routes.js",
        """const express = require("express");
const { Job } = require("./models");

const router = express.Router();

router.get("/v1/jobs", async (req, res) => {
  const { status, page = 1 } = req.query;
  const jobs = await Job.find(status ? { status } : {})
    .sort({ updatedAt: -1 }).skip((page - 1) * 50).limit(50).lean();
  res.json({ data: jobs, page: Number(page) });
});

module.exports = router;
""",
    ),
    "sql_query": (
        "pipeline_by_region.sql",
        """-- Weekly pipeline by region and rep (star schema: fact_deals, dim_rep, dim_date)
SELECT d.week_start,
       r.region,
       r.rep_name,
       SUM(f.amount) FILTER (WHERE f.stage = 'won')  AS won_amount,
       SUM(f.amount) FILTER (WHERE f.stage <> 'lost') AS open_pipeline,
       COUNT(*)                                      AS deals
FROM fact_deals f
JOIN dim_rep r  ON r.rep_id = f.rep_id
JOIN dim_date d ON d.date_id = f.created_date_id
GROUP BY 1, 2, 3
ORDER BY 1 DESC, 4 DESC;
""",
    ),
    "etl_job": (
        "load_crm.py",
        """from datetime import date

import pandas as pd
from google.cloud import bigquery


def run(day: date) -> int:
    rows = pd.DataFrame(crm_client.deals(updated_since=day))
    rows = rows.drop_duplicates("deal_id").assign(loaded_at=pd.Timestamp.utcnow())
    assert rows["amount"].ge(0).all(), "negative amounts"
    bigquery.Client().load_table_from_dataframe(rows, "raw.crm_deals").result()
    return len(rows)
""",
    ),
}
CODE["analysis_py"] = (
    "analysis.py",
    """import pandas as pd
from scipy import stats

df = pd.read_csv("responses.csv")
a, b = df[df.group == "A"].score, df[df.group == "B"].score
t, p = stats.ttest_ind(a, b, equal_var=False)
print(f"diff={b.mean() - a.mean():.2f}  p={p:.3f}  n={len(df)}")
print(df.groupby("segment").score.agg(["mean", "count"]).round(2))
""",
)
CODE["django_view"] = (
    "views.py",
    """from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import Request


@login_required
def my_requests(request):
    items = Request.objects.filter(owner=request.user).order_by("-updated_at")
    return render(request, "portal/requests.html", {"items": items})
""",
)
CODE["php_snippet"] = (
    "functions.php",
    """<?php
// Register an editable "case study" block for the marketing team.
add_action('init', function () {
    register_block_type(__DIR__ . '/blocks/case-study', [
        'render_callback' => fn($attrs) => sprintf(
            '<section class="case"><h3>%s</h3><p>%s</p></section>',
            esc_html($attrs['title'] ?? ''), esc_html($attrs['summary'] ?? '')
        ),
    ]);
});
""",
)
COMMENT = {".py": "#", ".ts": "//", ".tsx": "//", ".js": "//", ".sql": "--", ".php": "//"}


def default_kind(pid: str, p: dict) -> str:
    """Code sample matching the project's stack when its archetype defines no repo."""
    skills = set(p["skills"])
    if pid == "ai_ml":
        return "python_util"
    if pid == "data_analyst":
        return "analysis_py" if skills & {"python", "pandas", "statistics"} else "sql_query"
    if skills & {"php", "wordpress", "laravel"}:
        return "php_snippet"
    if "django" in skills:
        return "django_view"
    if skills & {"express.js", "mongodb"} or ("node.js" in skills and "react" not in skills):
        return "express_route"
    return "react_component"


def readme(p: dict, arch: dict, repo: str, filename: str) -> str:
    stack = ", ".join(f"`{s}`" for s in p["skills"])
    deliver = "\n".join(f"- {d}" for d in arch["deliverables"])
    return (
        f"# {repo}\n\nOpen-sourced, anonymised version of a project built for "
        f"{with_article(p['industry_noun'])} ({p['start'][:4]}).\n\n## Stack\n{stack}\n\n"
        f"## What it does\n{_cap(_fill(arch['approach'][0], p))}.\n\n## Components\n{deliver}\n\n"
        f"## Quick start\n```bash\ndocker compose up --build\n```\n\nEntry point: `{filename}`.\n\n"
        f"## Results in production\n{_cap(p['metric'])}.\n"
    )


# ----------------------------------------------------------------------------- CV

CV_TOP_SKILLS = 14


def cv_markdown(pid: str, persona: dict, projects: list[dict]) -> str:
    skills: dict[str, None] = dict.fromkeys(persona["base_skills"])
    for p in projects:
        skills.update(dict.fromkeys(p["skills"]))
    bullets = "\n".join(
        f"- **{p['start'][:7]}** - {p['title']} ({p['client']}): {p['metric']}."
        for p in sorted(projects, key=lambda p: p["start"], reverse=True)
    )
    return (
        f"# {persona['name']}\n\n{persona['headline']}  \n{persona['location']} · "
        f"{persona['years_experience']} years of experience\n\n## Summary\nFreelancer focused on "
        f"{persona['category'].replace('_', ' ')} work for small and mid-sized businesses. "
        f"I scope carefully, ship in small steps and measure results.\n\n"
        f"## Skills\n{', '.join(list(skills)[:CV_TOP_SKILLS])}\n\n"
        f"## Selected freelance engagements\n{bullets}\n\n## Education\n"
        f"BSc Computer Science (fictional institution for this synthetic persona)\n"
    )


def cv_pdf(md: str, path: Path) -> None:
    pdf = FPDF()
    pdf.set_creation_date(REF_NOW)
    pdf.set_producer("GigBid synthetic data generator")
    pdf.set_subject("SYNTHETIC persona CV - " + PROV)
    pdf.add_page()
    pdf.set_auto_page_break(True, margin=15)
    for line in md.splitlines():
        text = (
            line.replace("**", "").replace("·", "-").encode("latin-1", "replace").decode("latin-1")
        )
        if line.startswith("# "):
            pdf.set_font("Helvetica", "B", 18)
            pdf.multi_cell(0, 9, text[2:], new_x="LMARGIN", new_y="NEXT")
        elif line.startswith("## "):
            pdf.set_font("Helvetica", "B", 13)
            pdf.ln(2)
            pdf.multi_cell(0, 7, text[3:], new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, text.rstrip() or " ", new_x="LMARGIN", new_y="NEXT")
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(path))


# ----------------------------------------------------------------------------- main


def generate_persona(pid: str, persona: dict, out_root: Path = PERSONAS) -> dict:
    r = rng(f"personas:{pid}")
    out = out_root / pid
    projects = build_projects(pid, persona, r)
    by_key = {a["key"]: a for a in persona["archetypes"]}
    evidence: list[dict] = []

    def add(eid: str, etype: str, p: dict | None, title: str, text: str, named: list[str],
            rel_path: str, outcome: str | None) -> None:  # fmt: skip
        evidence.append(
            stamp(
                {
                    "id": eid,
                    "persona": pid,
                    "type": etype,
                    "project_id": p["project_id"] if p else None,
                    "title": title,
                    "path": rel_path,
                    "date": (p["end"] if p else iso(REF_NOW))[:10],
                    "client_industry": p["industry"] if p else None,
                    "outcome": outcome,
                    "skills": list(p["skills"]) if p else [],
                    "skills_named": named,
                    "text": text,
                },
                PROV,
            )
        )

    # Case studies
    for i, p in enumerate(projects, start=1):
        body, named = case_study(p, by_key[p["archetype"]], r)
        rel = f"case_studies/{i:02d}-{slug(p['title'])}.md"
        eid = f"{pid}:case:{i:02d}"
        meta = {"id": eid, "project_id": p["project_id"], "date": p["end"][:10],
                "client_industry": p["industry"], "synthetic": True, "provenance": PROV}  # fmt: skip
        write_text(out / rel, front_matter(meta, body))
        outcome = f"delivered; rated {p['rating']}/5" + ("; rehired" if p["rehired"] else "")
        add(eid, "case_study", p, p["title"], body, named, rel, outcome)
        p["evidence"] = [eid]

    # Reviews: one per project, plus second reviews from rehiring clients (20-40 total)
    reviews = []
    for p in projects:
        n_reviews = 2 if p["rehired"] and r.random() < 0.6 else 1
        for nth in range(n_reviews):
            rv = review(p, by_key[p["archetype"]], persona, r, nth)
            eid = f"{pid}:review:{len(reviews) + 1:02d}"
            reviews.append(stamp({"id": eid, "project_id": p["project_id"], **rv}, PROV))
            add(eid, "review", p, f"Review from {rv['reviewer']}", rv["text"], [],
                "reviews.jsonl", f"{rv['rating']}/5")  # fmt: skip
            p["evidence"].append(eid)
    write_jsonl(out / "reviews.jsonl", reviews)

    # Repos: prefer archetypes that define one, then fill to MIN..MAX with default kinds
    n_repos = r.randint(MIN_REPOS, MAX_REPOS)
    with_spec = [p for p in projects if by_key[p["archetype"]].get("repo")]
    seen_kinds: set[str] = set()
    chosen = []
    for p in with_spec:
        if by_key[p["archetype"]]["repo"]["name"] not in seen_kinds:
            seen_kinds.add(by_key[p["archetype"]]["repo"]["name"])
            chosen.append(p)
    rest = [p for p in projects if p not in chosen]
    r.shuffle(rest)
    chosen = (chosen + rest)[:n_repos]
    for p in sorted(chosen, key=lambda p: p["project_id"]):
        spec = by_key[p["archetype"]].get("repo")
        if spec and spec["name"] in seen_kinds:
            repo, kind = spec["name"], spec["kind"]
            seen_kinds.discard(spec["name"])
        else:
            repo, kind = f"{slug(p['archetype'])}-{slug(p['industry'])}", default_kind(pid, p)
        filename, code = CODE[kind]
        c = COMMENT[Path(filename).suffix]
        code_text = f"{c} SYNTHETIC sample code for GigBid persona {pid}. provenance: {PROV}\n" + (
            code.replace("{repo}", repo)
        )
        write_text(out / "repos" / repo / filename, code_text)
        rd = readme(p, by_key[p["archetype"]], repo, filename)
        write_text(
            out / "repos" / repo / "README.md",
            rd + f"\n<!-- synthetic: true; provenance: {PROV} -->\n",
        )
        add(f"{pid}:readme:{repo}", "readme", p, f"{repo} README", rd, list(p["skills"]),
            f"repos/{repo}/README.md", None)  # fmt: skip
        add(f"{pid}:code:{repo}", "code", p, f"{repo}/{filename}", code_text, [],
            f"repos/{repo}/{filename}", None)  # fmt: skip
        p["evidence"] += [f"{pid}:readme:{repo}", f"{pid}:code:{repo}"]
        p["repo"] = repo

    # CV (markdown + PDF): one evidence item covering every engagement
    md = cv_markdown(pid, persona, projects)
    write_text(out / "cv.md", front_matter({"synthetic": True, "provenance": PROV}, md))
    cv_pdf(md, out / "cv.pdf")
    add(f"{pid}:cv", "cv", None, f"CV - {persona['name']}", md, list(persona["base_skills"]),
        "cv.pdf", None)  # fmt: skip

    profile = stamp(
        {
            "persona": pid,
            "name": persona["name"],
            "headline": persona["headline"],
            "location": persona["location"],
            "years_experience": persona["years_experience"],
            "category": persona["category"],
            "floors": persona["floors"],
            "target_rate": persona["target_rate"],
            "skills": sorted(
                {s for p in projects for s in p["skills"]} | set(persona["base_skills"])
            ),
        },
        PROV,
    )
    write_json(out / "profile.json", profile)
    write_jsonl(out / "evidence.jsonl", evidence)
    write_json(out / "_meta" / "projects.json", [stamp(p, PROV) for p in projects])
    return {"persona": pid, "projects": len(projects), "reviews": len(reviews),
            "repos": len(chosen), "evidence": len(evidence)}  # fmt: skip


def main(out_root: Path = PERSONAS) -> list[dict]:
    summary = [generate_persona(pid, spec, out_root) for pid, spec in specs()["personas"].items()]
    for s in summary:
        print(s)
    return summary


if __name__ == "__main__":
    main()
