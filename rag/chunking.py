"""Chunking strategies. Every chunk keeps its document's id and metadata.

fixed       ~N-word windows with overlap over the whole text (V0, the naive baseline)
structured  respects structure: Markdown sections/paragraphs, one CV engagement per chunk,
            whole code files, whole reviews/proposals; long sections are split at sentence
            boundaries up to `max_words`. Each chunk is prefixed with its document title.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from rag.ingest.loaders import Document

SENT = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    index: int
    text: str  # what gets embedded / matched (title-prefixed for structured chunks)
    doc: Document

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()[:16]


def _words(text: str) -> list[str]:
    return text.split()


def fixed_chunks(doc: Document, size: int = 200, overlap: int = 40) -> list[Chunk]:
    words = _words(doc.text)
    if not words:
        return []
    step = max(1, size - overlap)
    out = []
    for i, start in enumerate(range(0, max(len(words) - overlap, 1), step)):
        out.append(Chunk(f"{doc.id}#f{i}", doc.id, i, " ".join(words[start : start + size]), doc))
    return out


def _split_long(text: str, max_words: int) -> list[str]:
    if len(_words(text)) <= max_words:
        return [text]
    parts, cur = [], []
    for s in SENT.split(text):
        if cur and len(_words(" ".join(cur + [s]))) > max_words:
            parts.append(" ".join(cur))
            cur = []
        cur.append(s)
    if cur:
        parts.append(" ".join(cur))
    return parts


def _sections(doc: Document) -> list[str]:
    if doc.type in {"code", "review", "proposal"}:
        return [doc.text]
    if doc.type == "cv":
        blocks = re.split(r"\n(?=- |• |## |[A-Z][a-z]+ [A-Z]|\d{4}-\d{2})", doc.text)
        return [b.strip() for b in blocks if b.strip()]
    blocks = re.split(r"\n(?=#{1,3} )|\n\s*\n", doc.text)
    return [b.strip() for b in blocks if b.strip() and not re.fullmatch(r"#+ .*", b.strip())] or [doc.text]


def structured_chunks(doc: Document, max_words: int = 220) -> list[Chunk]:
    out: list[Chunk] = []
    buf: list[str] = []

    def flush():
        if buf:
            body = "\n".join(buf)
            out.append(Chunk(f"{doc.id}#s{len(out)}", doc.id, len(out), f"{doc.title}\n{body}", doc))
            buf.clear()

    for sec in _sections(doc):
        for piece in _split_long(sec, max_words):
            if buf and len(_words(" ".join(buf + [piece]))) > max_words:
                flush()
            buf.append(piece)
        if doc.type == "cv":  # one CV engagement / section per chunk
            flush()
    flush()
    return out


def chunk_documents(docs: list[Document] | tuple[Document, ...], strategy: str, cfg: dict) -> list[Chunk]:
    if strategy == "fixed":
        return [c for d in docs for c in fixed_chunks(d, cfg["fixed_words"], cfg["fixed_overlap"])]
    return [c for d in docs for c in structured_chunks(d, cfg["max_words"])]
