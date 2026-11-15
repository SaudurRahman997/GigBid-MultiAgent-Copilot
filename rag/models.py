"""Embedding and reranking models (fastembed, ONNX on CPU) with a content-addressed disk cache.

Models come from agent/config.yaml (`embeddings`, `reranker`). Unit tests use HashEmbedder /
OverlapReranker so they never download a model; evals and deployment use the real ones.
Cache: <cache_dir>/<model-slug>/<sha256(text)>.npy (embeddings) and a JSON map for rerank
scores, so re-running an evaluation is fast and gives identical numbers.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Protocol

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "agent" / "config.yaml"
TOKEN = re.compile(r"[a-z0-9][a-z0-9+#.]*")


def _cfg() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _slug(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", model).strip("_")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


class Reranker(Protocol):
    name: str

    def score(self, query: str, passages: list[str]) -> list[float]: ...


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.where(norms == 0, 1.0, norms)


class FastEmbedEmbedder:
    def __init__(
        self,
        model: str,
        dim: int,
        query_prefix: str = "",
        doc_prefix: str = "",
        cache_dir: Path | None = None,
    ):
        self.name, self.dim = model, dim
        self.qp, self.dp = query_prefix, doc_prefix
        self.cache = (cache_dir or ROOT / "var" / "cache" / "rag") / "emb" / _slug(model)
        self.cache.mkdir(parents=True, exist_ok=True)
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(model_name=self.name)
        return self._model

    def _embed(self, texts: list[str]) -> np.ndarray:
        out: list[np.ndarray | None] = [None] * len(texts)
        missing = []
        for i, t in enumerate(texts):
            f = self.cache / f"{_sha(t)}.npy"
            if f.exists():
                out[i] = np.load(f)
            else:
                missing.append(i)
        if missing:
            with self._lock:
                vecs = list(self._load().embed([texts[i] for i in missing], batch_size=32))
            for i, v in zip(missing, vecs, strict=True):
                v = np.asarray(v, dtype=np.float32)
                np.save(self.cache / f"{_sha(texts[i])}.npy", v)
                out[i] = v
        return (
            _normalize(np.vstack(out).astype(np.float32))
            if texts
            else np.zeros((0, self.dim), np.float32)
        )

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self._embed([self.dp + t for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([self.qp + text])[0]


class FastEmbedReranker:
    def __init__(self, model: str, cache_dir: Path | None = None):
        self.name = model
        d = (cache_dir or ROOT / "var" / "cache" / "rag") / "rerank"
        d.mkdir(parents=True, exist_ok=True)
        self.cache_file = d / f"{_slug(model)}.json"
        self._scores: dict[str, float] = (
            json.loads(self.cache_file.read_text(encoding="utf-8"))
            if self.cache_file.exists()
            else {}
        )
        self._model = None
        self._lock = threading.Lock()
        self._dirty = 0

    def _load(self):
        if self._model is None:
            from fastembed.rerank.cross_encoder import TextCrossEncoder

            self._model = TextCrossEncoder(model_name=self.name)
        return self._model

    def score(self, query: str, passages: list[str]) -> list[float]:
        keys = [_sha(query + "\x00" + p) for p in passages]
        missing = [i for i, k in enumerate(keys) if k not in self._scores]
        if missing:
            with self._lock:
                scores = list(
                    self._load().rerank(query, [passages[i] for i in missing], batch_size=16)
                )
            for i, s in zip(missing, scores, strict=True):
                self._scores[keys[i]] = float(s)
            self._dirty += len(missing)
            if self._dirty >= 200:
                self.flush()
        return [self._scores[k] for k in keys]

    def flush(self) -> None:
        tmp = self.cache_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._scores), encoding="utf-8")
        tmp.replace(self.cache_file)
        self._dirty = 0


# ----------------------------------------------------------------------------- test doubles


class HashEmbedder:
    """Deterministic bag-of-words hashing embedder (tests only; no semantics)."""

    name = "hash-test"

    def __init__(self, dim: int = 256):
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, np.float32)
        for tok in TOKEN.findall(text.lower()):
            v[int(_sha(tok)[:8], 16) % self.dim] += 1.0
        return v

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return (
            _normalize(np.vstack([self._vec(t) for t in texts]))
            if texts
            else np.zeros((0, self.dim))
        )

    def embed_query(self, text: str) -> np.ndarray:
        return _normalize(self._vec(text)[None])[0]


class OverlapReranker:
    """Token-overlap 'cross-encoder' (tests only)."""

    name = "overlap-test"

    def score(self, query: str, passages: list[str]) -> list[float]:
        q = set(TOKEN.findall(query.lower()))
        return [len(q & set(TOKEN.findall(p.lower()))) / (1 + len(q)) for p in passages]


@lru_cache(maxsize=2)
def default_embedder() -> FastEmbedEmbedder:
    c = _cfg()
    e = c["embeddings"]
    return FastEmbedEmbedder(
        e["model"],
        int(e["dim"]),
        e.get("query_prefix", ""),
        e.get("doc_prefix", ""),
        ROOT / c["rag"]["cache_dir"],
    )


@lru_cache(maxsize=2)
def default_reranker() -> FastEmbedReranker:
    c = _cfg()
    return FastEmbedReranker(c["reranker"]["model"], ROOT / c["rag"]["cache_dir"])
