"""Loaders: raw portfolio files -> Documents with metadata.

Sources per persona folder (data/personas/<p>/ or an uploaded folder):
  cv.pdf                      PDF CV (pypdf text extraction)
  case_studies/*.md           Markdown + YAML front matter (id, project_id, date, client_industry)
  repos/<name>/README.md      READMEs        repos/<name>/<code file>   code samples
  reviews.jsonl               client reviews (rating)
  proposals.jsonl             past proposals (outcome won/replied/ignored)
Real repositories come in through the GitHub MCP loader (rag/ingest/github.py) as the same
Document shape.

Metadata on every document: persona, type, project, skills, date, client_industry, outcome.
Skills come from a sidecar index when one exists (synthetic personas: evidence.jsonl), otherwise
from taxonomy keyword detection on the text, so uploaded work gets skills too.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

import yaml
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".sql", ".php"}


@dataclass(frozen=True)
class Document:
    id: str
    persona: str
    type: str  # case_study | review | readme | code | cv | proposal
    title: str
    text: str
    source: str
    date: str | None = None
    outcome: str | None = None
    project_id: str | None = None
    client_industry: str | None = None
    skills: tuple[str, ...] = field(default_factory=tuple)

    @property
    def metadata(self) -> dict:
        return {
            "persona": self.persona,
            "type": self.type,
            "project": self.project_id,
            "skills": list(self.skills),
            "date": self.date,
            "client_industry": self.client_industry,
            "outcome": self.outcome,
            "source": self.source,
            "title": self.title,
        }


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").split("\n") if x]


def _front_matter(text: str) -> tuple[dict, str]:
    if text.startswith("---\n"):
        head, _, body = text[4:].partition("\n---\n")
        return yaml.safe_load(head) or {}, body.strip()
    return {}, text


@lru_cache(maxsize=1)
def _taxonomy_surfaces() -> dict[str, str]:
    """surface form -> canonical skill, from data/processed/skill_taxonomy.json."""
    path = ROOT / "data" / "processed" / "skill_taxonomy.json"
    if not path.exists():
        return {}
    tax = json.loads(path.read_text(encoding="utf-8"))
    surfaces = {s: s for cat in tax["categories"].values() for s in cat["skills"]}
    surfaces |= {a: c for a, c in tax["aliases"].items() if c in surfaces}
    stop = set(tax.get("text_stoplist", [])) | set(tax.get("text_generic_removed", []))
    return {k: v for k, v in surfaces.items() if k not in stop and len(k) >= 3}


def detect_skills(text: str, limit: int = 15) -> tuple[str, ...]:
    low = f" {text.lower()} "
    found = []
    for surface, canon in _taxonomy_surfaces().items():
        if canon not in found and re.search(rf"(?<![a-z0-9]){re.escape(surface)}(?![a-z0-9])", low):
            found.append(canon)
            if len(found) >= limit:
                break
    return tuple(sorted(found))


def pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def load_folder(folder: Path, persona: str) -> list[Document]:
    """All documents of one portfolio folder, enriched from evidence.jsonl when present."""
    sidecar = {e["id"]: e for e in _read_jsonl(folder / "evidence.jsonl")}
    docs: list[Document] = []

    def enrich(doc: Document) -> Document:
        meta = sidecar.get(doc.id)
        if meta:
            return replace(
                doc,
                skills=tuple(meta.get("skills") or ()),
                outcome=meta.get("outcome") or doc.outcome,
                project_id=meta.get("project_id") or doc.project_id,
                client_industry=meta.get("client_industry") or doc.client_industry,
                date=meta.get("date") or doc.date,
            )
        return replace(doc, skills=doc.skills or detect_skills(doc.title + " " + doc.text))

    cv = folder / "cv.pdf"
    if cv.exists():
        docs.append(
            Document(
                id=f"{persona}:cv",
                persona=persona,
                type="cv",
                title="CV",
                text=pdf_text(cv),
                source="cv.pdf",
            )
        )

    for f in sorted((folder / "case_studies").glob("*.md")):
        meta, body = _front_matter(f.read_text(encoding="utf-8"))
        title = next((ln[2:].strip() for ln in body.splitlines() if ln.startswith("# ")), f.stem)
        docs.append(
            Document(
                id=meta.get("id", f"{persona}:case:{f.stem}"),
                persona=persona,
                type="case_study",
                title=title,
                text=body,
                source=f"case_studies/{f.name}",
                date=str(meta["date"]) if meta.get("date") else None,
                project_id=meta.get("project_id"),
                client_industry=meta.get("client_industry"),
            )
        )

    for repo in sorted(p for p in (folder / "repos").glob("*") if p.is_dir()):
        readme = repo / "README.md"
        if readme.exists():
            text = re.sub(r"<!--.*?-->", "", readme.read_text(encoding="utf-8"), flags=re.S).strip()
            docs.append(
                Document(
                    id=f"{persona}:readme:{repo.name}",
                    persona=persona,
                    type="readme",
                    title=f"{repo.name} README",
                    text=text,
                    source=f"repos/{repo.name}/README.md",
                )
            )
        for code in sorted(c for c in repo.iterdir() if c.suffix in CODE_SUFFIXES):
            docs.append(
                Document(
                    id=f"{persona}:code:{repo.name}",
                    persona=persona,
                    type="code",
                    title=f"{repo.name}/{code.name}",
                    text=code.read_text(encoding="utf-8"),
                    source=f"repos/{repo.name}/{code.name}",
                )
            )

    for r in _read_jsonl(folder / "reviews.jsonl"):
        docs.append(
            Document(
                id=r["id"],
                persona=persona,
                type="review",
                title=f"Review from {r['reviewer']}",
                text=r["text"],
                source="reviews.jsonl",
                date=str(r.get("date", ""))[:10] or None,
                outcome=f"{r['rating']}/5",
                project_id=r.get("project_id"),
            )
        )

    for p in _read_jsonl(folder / "proposals.jsonl"):
        docs.append(
            Document(
                id=p["id"],
                persona=persona,
                type="proposal",
                title=p["job_title"],
                text=p["text"],
                source="proposals.jsonl",
                date=p.get("date"),
                outcome=p.get("outcome"),
                skills=tuple(p.get("skills") or ()),
            )
        )

    return [enrich(d) for d in docs]


@lru_cache(maxsize=16)
def load_persona(persona: str, data_dir: str = str(ROOT / "data")) -> tuple[Document, ...]:
    return tuple(load_folder(Path(data_dir) / "personas" / persona, persona))
