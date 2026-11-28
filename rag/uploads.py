"""Work a signed-in user adds to their portfolio from the web UI (assignment B1).

Files live in <GIGBID_UPLOAD_DIR>/<user id>/<persona>/<content hash>__<name>, so one user never
sees another's uploads and adding the same content twice changes nothing. The API writes them; the
Portfolio MCP server reads them for the user named by the X-GigBid-Tenant header.

Re-indexing is incremental where it is expensive: dense indexes embed only chunks whose content
hash is new (rag.models caches by content; PgVectorIndex.sync compares hashes). The in-memory
BM25 index is rebuilt from the user's documents when their upload set changes.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TENANT = re.compile(r"u_[0-9a-f]{12}")  # the API's user ids; anything else gets no uploads
KINDS = {".md": "case_study", ".pdf": "cv", ".py": "code", ".ts": "code", ".tsx": "code",
         ".js": "code", ".sql": "code", ".php": "code"}  # fmt: skip
MAX_BYTES = 200_000
MAX_FILES = 50
MIN_TEXT = 40
STORED = re.compile(r"([0-9a-f]{12})__(.+)")


class UploadError(ValueError):
    """The file cannot be accepted; the message is safe to show to the user."""


@dataclass(frozen=True)
class Upload:
    id: str  # evidence id, e.g. ai_ml:upload:1a2b3c4d5e6f
    filename: str
    type: str
    title: str
    text: str


def upload_root() -> Path:
    return Path(os.environ.get("GIGBID_UPLOAD_DIR") or ROOT / "var" / "uploads")


def valid_tenant(tenant: str | None) -> bool:
    return bool(tenant and TENANT.fullmatch(tenant))


def _folder(persona: str, tenant: str) -> Path:
    if not valid_tenant(tenant) or not re.fullmatch(r"[a-z_]+", persona):
        raise UploadError("unknown user or profile")
    return upload_root() / tenant / persona


def safe_name(filename: str) -> str:
    base = re.split(r"[\\/]", filename)[-1]
    return re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip(".-")[:80]


def extract_text(suffix: str, data: bytes) -> str:
    if suffix == ".pdf":
        from pypdf import PdfReader

        try:
            pages = PdfReader(io.BytesIO(data)).pages
            return "\n".join(page.extract_text() or "" for page in pages).strip()
        except Exception as exc:  # noqa: BLE001 - any parser failure means a bad file
            raise UploadError("could not read this PDF") from exc
    try:
        return data.decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise UploadError("the file is not UTF-8 text") from exc


def _parse(persona: str, path: Path) -> Upload | None:
    match = STORED.fullmatch(path.name)
    if not match or path.suffix.lower() not in KINDS:
        return None
    digest, name = match.groups()
    text = extract_text(path.suffix.lower(), path.read_bytes())
    heading = next((ln[2:].strip() for ln in text.splitlines() if ln.startswith("# ")), None)
    return Upload(
        f"{persona}:upload:{digest}", name, KINDS[path.suffix.lower()], heading or name, text
    )


def _files(persona: str, tenant: str | None) -> list[Path]:
    if not valid_tenant(tenant):
        return []
    folder = _folder(persona, tenant)
    return (
        sorted(p for p in folder.iterdir() if STORED.fullmatch(p.name)) if folder.is_dir() else []
    )


def fingerprint(persona: str, tenant: str | None) -> tuple[str, ...]:
    """Changes exactly when the user's upload set changes (names start with the content hash)."""
    return tuple(p.name for p in _files(persona, tenant))


def list_uploads(persona: str, tenant: str | None) -> list[Upload]:
    return [u for p in _files(persona, tenant) if (u := _parse(persona, p))]


def save_upload(persona: str, tenant: str, filename: str, data: bytes) -> Upload:
    folder = _folder(persona, tenant)
    name = safe_name(filename)
    suffix = Path(name).suffix.lower()
    if suffix not in KINDS:
        raise UploadError(f"unsupported file type; use one of {', '.join(sorted(KINDS))}")
    if len(data) > MAX_BYTES:
        raise UploadError(f"file is larger than {MAX_BYTES // 1000} KB")
    if len(extract_text(suffix, data)) < MIN_TEXT:
        raise UploadError("the file has too little readable text to use as evidence")
    digest = hashlib.sha256(data).hexdigest()[:12]
    existing = _files(persona, tenant)
    same = next((p for p in existing if p.name.startswith(digest)), None)
    if same is None:
        if len(existing) >= MAX_FILES:
            raise UploadError(f"upload limit of {MAX_FILES} files reached")
        folder.mkdir(parents=True, exist_ok=True)
        same = folder / f"{digest}__{name}"
        same.write_bytes(data)
    return _parse(persona, same)


def delete_upload(persona: str, tenant: str, upload_id: str) -> bool:
    digest = upload_id.rsplit(":", 1)[-1]
    for path in _files(persona, tenant):
        if path.name.startswith(f"{digest}__") and upload_id == f"{persona}:upload:{digest}":
            path.unlink()
            return True
    return False


def documents(persona: str, tenant: str | None, cls: type) -> list:
    """The uploads as `cls` documents (rag.corpus.Document or rag.ingest.loaders.Document)."""
    from rag.ingest.loaders import detect_skills

    return [
        cls(
            id=u.id,
            persona=persona,
            type=u.type,
            title=u.title,
            text=u.text,
            source=f"uploads/{u.filename}",
            skills=detect_skills(f"{u.title} {u.text}"),
        )
        for u in list_uploads(persona, tenant)
    ]
