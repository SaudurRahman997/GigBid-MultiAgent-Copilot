"""Profile every downloaded Kaggle dataset into data/processed/profiles/<dataset>.md.

For each tabular file: row count, every column with dtype, null %, distinct count, and 5 seeded
sample rows (long text truncated). Non-tabular files (notes, metadata) are listed with a preview.
Nothing here assumes column names; it is the first look at the data.

Usage: uv run python -m data.generators.profile_datasets [--only <dataset_dir_name>]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "profiles"
SEED = 0
TRUNC = 120
TABULAR = {".csv", ".xlsx", ".xls", ".parquet"}


def read_table(path: Path) -> pd.DataFrame:
    if path.suffix == ".csv":
        return pd.read_csv(path, low_memory=False)
    if path.suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, engine="calamine")
    return pd.read_parquet(path)


def _short(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    text = text.replace("\n", " ").replace("|", "/")
    return text if len(text) <= TRUNC else text[: TRUNC - 1] + "…"


def profile_table(path: Path) -> str:
    df = read_table(path)
    n = len(df)
    lines = [f"### `{path.name}`", "", f"- rows: **{n:,}**", f"- columns: **{df.shape[1]}**"]
    dup = int(df.duplicated().sum()) if n <= 2_000_000 else -1
    lines.append(f"- exact duplicate rows: {dup:,}")
    lines += [
        "",
        "| # | column | dtype | null % | distinct | example |",
        "|---|---|---|---|---|---|",
    ]
    for i, col in enumerate(df.columns):
        s = df[col]
        null_pct = 100 * s.isna().mean() if n else 0.0
        try:
            distinct = f"{s.nunique(dropna=True):,}"
        except TypeError:  # unhashable cells (lists/dicts)
            distinct = "n/a"
        example = _short(s.dropna().iloc[0]) if s.notna().any() else ""
        lines.append(f"| {i} | `{col}` | {s.dtype} | {null_pct:.1f} | {distinct} | {example} |")

    numeric = df.select_dtypes("number")
    if not numeric.empty:
        desc = numeric.describe(percentiles=[0.25, 0.5, 0.75]).T.round(2)
        lines += ["", "Numeric summary:", "", desc.to_markdown()]

    sample = df.sample(min(5, n), random_state=SEED) if n else df
    lines += ["", "5 sample rows (seeded, text truncated):", ""]
    lines.append(sample.map(_short).to_markdown(index=False))
    return "\n".join(lines) + "\n"


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml").decode("utf-8")
    xml = re.sub(r"</w:p>", "\n", xml)
    return re.sub(r"<[^>]+>", "", xml)


def profile_other(path: Path) -> str:
    raw = path.read_bytes()
    if path.suffix.lower() == ".docx":
        text = _docx_text(path).strip()
        return f"### `{path.name}` (docx, {len(raw):,} bytes)\n\n```text\n{text[:4000]}\n```\n"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    preview = text.replace("\x00", "")[:1500].strip()
    return f"### `{path.name}` (non-tabular, {len(raw):,} bytes)\n\n```text\n{preview}\n```\n"


def profile_dataset(ds_dir: Path) -> Path:
    meta_path = ds_dir / "dataset-metadata.json"
    info = (
        json.loads(meta_path.read_text(encoding="utf-8")).get("info", {})
        if meta_path.exists()
        else {}
    )
    ref = f"{info.get('ownerUser', '?')}/{info.get('datasetSlug', ds_dir.name)}"
    licences = ", ".join(lic.get("name", "?") for lic in info.get("licenses", [])) or "unknown"
    downloaded = (
        (ds_dir / ".downloaded").read_text().strip() if (ds_dir / ".downloaded").exists() else "?"
    )

    files = sorted(p for p in ds_dir.iterdir() if p.is_file() and not p.name.startswith("."))
    parts = [
        f"# Profile: {ref}",
        "",
        f"- source: https://www.kaggle.com/datasets/{ref}",
        f"- title: {info.get('title', '?')}",
        f"- subtitle: {info.get('subtitle', '')}",
        f"- licence (from Kaggle metadata): **{licences}**",
        f"- downloaded (UTC): {downloaded}",
        "",
        "## Files",
        "",
        "| file | bytes |",
        "|---|---|",
        *[f"| `{p.name}` | {p.stat().st_size:,} |" for p in files],
        "",
        "## Contents",
        "",
    ]
    for p in files:
        if p.name == "dataset-metadata.json":
            continue
        print(f"  profiling {p.name} ...", flush=True)
        if p.suffix.lower() in TABULAR:
            # ahmedmyalo ships the same table as .csv and .xlsx; profile the csv only.
            if p.suffix == ".xlsx" and p.with_suffix(".csv").exists():
                parts.append(
                    f"### `{p.name}`\n\nSame table as `{p.with_suffix('.csv').name}`; skipped.\n"
                )
                continue
            parts.append(profile_table(p))
        else:
            parts.append(profile_other(p))

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{ds_dir.name}.md"
    out.write_text("\n".join(parts), encoding="utf-8")
    return out


JOB_SETS = {
    "50k": ("asaniczka__upwork-job-postings-dataset-2024-50k-records", "link"),
    "200k": ("asaniczka__all-jobs-on-upwork-200k-plus", "link"),
    "60k": ("ahmedmyalo__upwork-freelance-jobs-60k", "Job_URL"),
}


def _job_ids(ds: str, col: str) -> set[str]:
    """Upwork job ids (the stable `~<hex>` part of the URL; slugs and query strings vary)."""
    ids: set[str] = set()
    for f in sorted((RAW / ds).glob("*.csv")):
        s = pd.read_csv(f, usecols=[col], low_memory=False)[col].dropna().astype(str)
        # asaniczka URLs encode "~" as "%7E"; ahmedmyalo URLs keep the literal "~".
        found = s.str.extract(r"(?:~|%7[Ee])([0-9a-f]{10,})", expand=False).dropna()
        ids |= set(found)
    return ids


def overlap_report() -> Path:
    """How many job postings the job datasets share, keyed by Upwork job id."""
    ids = {k: _job_ids(ds, col) for k, (ds, col) in JOB_SETS.items()}
    rows = [
        "# Overlap between job-posting datasets",
        "",
        "Keyed by the `~<hex>` Upwork job id extracted from the job URL.",
        "",
        "| A | B | unique ids A | unique ids B | shared | shared % of A |",
        "|---|---|---|---|---|---|",
    ]
    keys = list(ids)
    for i, a in enumerate(keys):
        for b in keys[i + 1 :]:
            shared = len(ids[a] & ids[b])
            pct = 100 * shared / len(ids[a]) if ids[a] else 0.0
            rows.append(
                f"| {a} | {b} | {len(ids[a]):,} | {len(ids[b]):,} | {shared:,} | {pct:.1f} |"
            )
    out = OUT / "_overlap.md"
    out.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="profile a single dataset directory name")
    args = ap.parse_args(argv)
    if not RAW.exists():
        print("data/raw not found; run scripts/download_kaggle.sh first", file=sys.stderr)
        return 1
    dirs = sorted(d for d in RAW.iterdir() if d.is_dir())
    if args.only:
        dirs = [d for d in dirs if d.name == args.only]
    for d in dirs:
        print(f"[{d.name}]", flush=True)
        print(f"  -> {profile_dataset(d).relative_to(ROOT)}")
    if not args.only:
        print(f"  -> {overlap_report().relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
