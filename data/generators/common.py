"""Shared helpers for the synthetic-data generators.

Determinism: every generator draws from `rng(name)`, a `random.Random` seeded with the string
"<SEED>:<name>" (string seeds hash via SHA-512, so they are stable across runs and platforms).
Time is pinned to REF_NOW, never the wall clock.

Provenance: "<generator>@<git blob sha>" where the sha is `git hash-object` of the generator's
source file. It identifies the exact generator version without depending on the commit, so the
same code + seed always yields byte-identical files.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import random
import re
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

SEED = 20261115
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
SYNTHETIC = DATA / "synthetic"
PERSONAS = DATA / "personas"
DEVSET = DATA / "devset"
HELDOUT = DATA / "heldout"  # git-ignored: stand-in for the hidden test set
POLICY = DATA / "policy_pack" / "policy.yaml"
SPECS = Path(__file__).with_name("persona_specs.yaml")
REF_NOW = datetime(2026, 11, 1, 9, 0, tzinfo=UTC)


def rng(name: str, seed: int = SEED) -> random.Random:
    return random.Random(f"{seed}:{name}")


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def provenance(generator_file: str | Path) -> str:
    p = Path(generator_file)
    return f"{p.stem}@{git_blob_sha(p)[:12]}"


def stamp(record: dict, prov: str) -> dict:
    return {**record, "synthetic": True, "provenance": prov}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# ----------------------------------------------------------------------------- writing


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8", newline="\n")


def write_json(path: Path, obj: Any) -> None:
    write_text(path, json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, default=str))


def write_jsonl(path: Path, records: list[dict]) -> None:
    lines = [json.dumps(r, sort_keys=True, ensure_ascii=False, default=str) for r in records]
    write_text(path, "\n".join(lines))


def read_jsonl(path: Path) -> list[dict]:
    # split("\n"), not splitlines(): JSON strings may contain U+2028 / U+0085, which
    # splitlines() treats as line breaks.
    return [json.loads(line) for line in path.read_text(encoding="utf-8").split("\n") if line]


def front_matter(meta: dict, body: str) -> str:
    head = yaml.safe_dump(meta, sort_keys=True, allow_unicode=True, width=100).strip()
    return f"---\n{head}\n---\n\n{body.strip()}\n"


def parse_front_matter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    head, _, body = text[4:].partition("\n---\n")
    return yaml.safe_load(head) or {}, body


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_manifest(root: Path, name: str = "MANIFEST.json") -> dict:
    files = sorted(
        p for p in root.rglob("*") if p.is_file() and p.name != name and not p.name.startswith(".")
    )
    manifest = {p.relative_to(root).as_posix(): sha256_file(p) for p in files}
    write_json(root / name, manifest)
    return manifest


# ----------------------------------------------------------------------------- inputs


@lru_cache(maxsize=1)
def specs() -> dict:
    return yaml.safe_load(SPECS.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def policy() -> dict:
    return yaml.safe_load(POLICY.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def client_priors() -> dict:
    return json.loads((PROCESSED / "client_priors.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def pricing() -> pd.DataFrame:
    return pd.read_parquet(PROCESSED / "pricing_stats.parquet")


def sample_quantile(table: dict, levels: list[float], r: random.Random) -> float:
    """Inverse-CDF sample from a quantile table by linear interpolation."""
    qs = table["quantiles"]
    u = r.random()
    i = min(max(bisect.bisect_right(levels, u) - 1, 0), len(levels) - 2)
    lo, hi = levels[i], levels[i + 1]
    frac = (u - lo) / (hi - lo) if hi > lo else 0.0
    return qs[i] + frac * (qs[i + 1] - qs[i])


def weighted_choice(r: random.Random, weights: dict[str, float]) -> str:
    keys = sorted(weights)
    return r.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def price_band(category: str, skills: list[str], pay_type: str, min_n: int = 100) -> dict:
    """Fair band = p25..p75 of real prices: first skill with n >= min_n, else the category."""
    df = pricing()
    df = df[df["pay_type"] == pay_type]
    for s in skills:
        row = df[(df["group_type"] == "skill") & (df["group"] == s) & (df["n"] >= min_n)]
        if not row.empty:
            r0 = row.iloc[0]
            return _band(r0, f"skill:{s}")
    row = df[(df["group_type"] == "category") & (df["group"] == category)]
    if row.empty:
        row = df[df["group_type"] == "all"]
    return _band(row.iloc[0], f"category:{category}")


def _band(row: pd.Series, source: str) -> dict:
    return {
        "low": float(row["p25"]),
        "high": float(row["p75"]),
        "median": float(row["p50"]),
        "p90": float(row["p90"]),
        "n": int(row["n"]),
        "source": source,
    }


def connects_cost(pay_type: str, budget: float | None, hourly_high: float | None) -> int:
    """Connects needed to bid, from the policy pack's tier table."""
    tiers = policy()["connects"]["tiers"][pay_type]
    value = budget if pay_type == "fixed" else hourly_high
    if value is None:
        return int(policy()["connects"]["default"])
    for tier in tiers:
        if value < tier["below"]:
            return int(tier["connects"])
    return int(tiers[-1]["connects"])
