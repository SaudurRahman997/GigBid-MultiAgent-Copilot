"""Clean the Kaggle data into the tables GigSim and the generators build on.

Inputs  (data/raw/, see profiles in data/processed/profiles/):
  50k job postings (asaniczka), 60k jobs with skill tags (ahmedmyalo), 200k+ job postings
  (asaniczka, titles + prices only), 1.3M contracts (asaniczka),
  12k freelancer priors (sarveshchhetri).

Outputs (data/processed/):
  jobs_corpus.parquet     real job posts with description, normalised pay, skills, category
                          (git-ignored: large, rebuilt by `make seed`)
  pricing_stats.parquet   price percentiles per category and per skill, hourly vs fixed
  skill_taxonomy.json     categories -> canonical skills with observed frequencies, aliases
  client_priors.json      quantile tables for synthesising clients (spend, rating, hires, ...)
  freelancer_priors.json  quantile tables for rates / success per primary skill
  preprocess_report.json  row counts after every step (cited by docs/DATA_CARD.md)
  MANIFEST.json           sha256 of every output (determinism check)

All amounts are USD: every source is Upwork, which quotes USD. No randomness is used here.

Usage: uv run python -m data.generators.preprocess
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
TAXONOMY_SEED = Path(__file__).with_name("taxonomy.yaml")

DS_50K = RAW / "asaniczka__upwork-job-postings-dataset-2024-50k-records"
DS_200K = RAW / "asaniczka__all-jobs-on-upwork-200k-plus"
DS_60K = RAW / "ahmedmyalo__upwork-freelance-jobs-60k"
DS_CONTRACTS = RAW / "asaniczka__freelance-contracts-dataset-1-3-million-entries"
DS_FREELANCERS = RAW / "sarveshchhetri__freelancer-success-earnings-and-churn-prediction"

# Sanity limits for prices (USD). Outside these a value is treated as a data error.
FIXED_MIN, FIXED_MAX = 5.0, 1_000_000.0
HOURLY_MIN, HOURLY_MAX = 3.0, 500.0
MIN_TAG_FREQ = 15  # a 60k skill tag joins the vocabulary if seen at least this often
MIN_GROUP_N = 30  # minimum sample size for a pricing_stats row
TEXT_MIN_N, TEXT_MIN_PRECISION = 400, 0.15  # generic-word filter for free-text skill matching
LEARN_MIN_N, LEARN_MIN_SHARE = 15, 0.60  # tag -> category learned from co-occurrence
TITLE_CLF_MIN_CONF = 0.60  # title classifier confidence needed to leave 'other'
QUANTILES = [round(q, 2) for q in np.linspace(0, 1, 21)]  # 0.00, 0.05, ..., 1.00
PCTS = {"p10": 0.10, "p25": 0.25, "p50": 0.50, "p75": 0.75, "p90": 0.90}
OTHER = "other"


# ----------------------------------------------------------------------------- parsing helpers

_MONEY = re.compile(r"\$?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kK])?")


def parse_money(value: object) -> float | None:
    """'$2,500 ' -> 2500.0, '$1.5k' -> 1500.0, '0' -> 0.0, NaN/'' -> None."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    m = _MONEY.search(str(value))
    if not m:
        return None
    amount = float(m.group(1).replace(",", ""))
    return amount * 1000 if m.group(2) else amount


def parse_rate_range(value: object) -> tuple[float | None, float | None]:
    """'$10.00-$45.00' -> (10.0, 45.0); '$20' -> (20.0, None)."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None, None
    parts = [parse_money(p) for p in str(value).split("-")]
    parts = [p for p in parts if p is not None]
    if not parts:
        return None, None
    return parts[0], (parts[1] if len(parts) > 1 else None)


def job_id_from_url(url: object) -> str | None:
    """Stable Upwork job id: the hex after '~' (or URL-encoded '%7E')."""
    m = re.search(r"(?:~|%7[Ee])([0-9a-f]{10,})", str(url))
    return m.group(1) if m else None


def norm_text(text: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(text).lower())).strip()


def norm_skill(text: object) -> str:
    return re.sub(r"\s+", " ", str(text).strip().lower())


def to_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in {"true", "false"}:
        return value.strip().lower() == "true"
    return None


def hourly_mid(low: float | None, high: float | None) -> float | None:
    vals = [v for v in (low, high) if v is not None and not np.isnan(v)]
    return float(np.mean(vals)) if vals else None


# ----------------------------------------------------------------------------- taxonomy


class Taxonomy:
    """Skill vocabulary, alias map and skill -> category lookup."""

    def __init__(self, seed: dict, tag_counts: Counter[str]):
        self.aliases: dict[str, str] = {
            norm_skill(k): norm_skill(v) for k, v in seed["aliases"].items()
        }
        self.stoplist = {norm_skill(s) for s in seed.get("text_stoplist", [])}
        self.categories: list[str] = list(seed["categories"])
        self.labels = {c: seed["categories"][c]["label"] for c in self.categories}
        self.skill_category: dict[str, str] = {}
        for cat in self.categories:
            for s in seed["categories"][cat]["skills"]:
                self.skill_category.setdefault(self.canon(s), cat)
        # Vocabulary = seed skills + frequent real tags (canonicalised).
        self.tag_counts = Counter({self.canon(k): 0 for k in self.skill_category})
        for tag, n in tag_counts.items():
            self.tag_counts[self.canon(tag)] += n
        self.vocab = {s for s, n in self.tag_counts.items() if n >= MIN_TAG_FREQ}
        self.vocab |= set(self.skill_category)
        # Surface forms usable in free text: vocab + aliases, minus ambiguous ones.
        surface = {s: s for s in self.vocab} | {
            a: c for a, c in self.aliases.items() if c in self.vocab
        }
        self.surface = {k: v for k, v in surface.items() if k not in self.stoplist and len(k) >= 2}
        self.max_ngram = max(len(k.split()) for k in self.surface)
        self.text_generic: set[str] = set()
        self.learned: set[str] = set()

    def canon(self, skill: object) -> str:
        s = norm_skill(skill)
        return self.aliases.get(s, s)

    def skills_in_text(self, text: object) -> list[str]:
        """Canonical skills mentioned in free text, by n-gram lookup (order of first mention)."""
        tokens = [t.strip(".") for t in re.findall(r"[a-z0-9][a-z0-9+#./-]*", str(text).lower())]
        tokens = [t for t in tokens if t]
        found: dict[str, None] = {}
        for i in range(len(tokens)):
            for n in range(self.max_ngram, 0, -1):
                gram = " ".join(tokens[i : i + n])
                hit = self.surface.get(gram)
                if hit:
                    found.setdefault(hit, None)
                    break
        return list(found)

    def category_of(self, skills: list[str], title: str = "") -> str:
        """Category with the most matching skills; title skills count double; tie -> seed order."""
        score = Counter()
        for s in skills:
            if s in self.skill_category:
                score[self.skill_category[s]] += 1
        for s in self.skills_in_text(title):
            if s in self.skill_category:
                score[self.skill_category[s]] += 2
        if not score:
            return OTHER
        best = max(score.values())
        return next(c for c in self.categories if score.get(c) == best)

    def refine(self, titles: list[str], texts: list[str], tag_lists: list[list[str]]) -> dict:
        """Two data-driven passes over jobs that have both free text and explicit skill tags.

        1. Text precision: a surface form that appears in >= TEXT_MIN_N job texts but whose skill
           is tagged on < TEXT_MIN_PRECISION of those jobs is generic ("business") -> stop
           inferring it from free text.
        2. Learned categories: a tag without a seed category gets the category it co-occurs with
           in >= LEARN_MIN_SHARE of its (>= LEARN_MIN_N) jobs, using seed-based categories.
        """
        canon_tags = [{self.canon(t) for t in tags} for tags in tag_lists]
        in_text: Counter[str] = Counter()
        with_tag: Counter[str] = Counter()
        for text, tags in zip(texts, canon_tags, strict=True):
            for s in self.skills_in_text(text):
                in_text[s] += 1
                with_tag[s] += s in tags
        generic = {
            s
            for s, n in in_text.items()
            if n >= TEXT_MIN_N
            and with_tag[s] / n < TEXT_MIN_PRECISION
            and s not in self.skill_category  # hand-picked seed skills are always kept
        }
        self.surface = {k: v for k, v in self.surface.items() if v not in generic}
        self.text_generic = generic

        seed_cats = [
            self.category_of(sorted(tags), title)
            for tags, title in zip(canon_tags, titles, strict=True)
        ]
        co: dict[str, Counter[str]] = {}
        for tags, cat in zip(canon_tags, seed_cats, strict=True):
            if cat == OTHER:
                continue
            for t in tags:
                if t in self.vocab and t not in self.skill_category:
                    co.setdefault(t, Counter())[cat] += 1
        learned = {}
        for tag, counts in co.items():
            n = sum(counts.values())
            cat, top = max(counts.items(), key=lambda kv: (kv[1], -self.categories.index(kv[0])))
            if n >= LEARN_MIN_N and top / n >= LEARN_MIN_SHARE:
                learned[tag] = cat
        self.skill_category.update(learned)
        self.learned = set(learned)
        return {"text_generic_removed": len(generic), "learned_category_skills": len(learned)}

    def to_json(self) -> dict:
        labels = self.labels | {OTHER: "Other"}
        cats: dict[str, dict] = {
            c: {"label": labels[c], "skills": {}} for c in [*self.categories, OTHER]
        }
        for s in sorted(self.vocab):
            cat = self.skill_category.get(s, OTHER)
            cats[cat]["skills"][s] = int(self.tag_counts.get(s, 0))
        return {
            "version": 1,
            "min_tag_freq": MIN_TAG_FREQ,
            "categories": cats,
            "learned_category_skills": sorted(self.learned),
            "aliases": dict(sorted(self.aliases.items())),
            "text_stoplist": sorted(self.stoplist),
            "text_generic_removed": sorted(self.text_generic),
        }


@lru_cache(maxsize=1)
def load_seed() -> dict:
    return yaml.safe_load(TAXONOMY_SEED.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- loaders

JOB_COLUMNS = [
    "job_id", "source", "title", "description", "published_at", "pay_type", "budget_usd",
    "hourly_low", "hourly_high", "country", "tags", "experience_level", "connects_old",
    "connects_new", "applicants", "payment_verified", "client_spent_usd", "client_rating",
    "client_feedback_count", "client_hires",
]  # fmt: skip


def load_50k() -> pd.DataFrame:
    d = pd.read_csv(DS_50K / "upwork-jobs.csv", low_memory=False)
    is_hourly = d["is_hourly"].map(to_bool)
    out = pd.DataFrame(
        {
            "job_id": d["link"].map(job_id_from_url),
            "source": "asaniczka_50k",
            "title": d["title"],
            "description": d["description"],
            "published_at": pd.to_datetime(d["published_date"], utc=True, errors="coerce"),
            "pay_type": np.where(is_hourly.eq(True), "hourly",
                                 np.where(is_hourly.eq(False), "fixed", "unknown")),
            "budget_usd": d["budget"],
            "hourly_low": d["hourly_low"],
            "hourly_high": d["hourly_high"],
            "country": d["country"],
        }
    )  # fmt: skip
    return out.reindex(columns=JOB_COLUMNS)


def load_60k() -> pd.DataFrame:
    d = pd.read_csv(DS_60K / "Final_Upwork_Dataset.csv", low_memory=False)
    tag_cols = [f"Category_{i}" for i in range(1, 10)]
    tags = d[tag_cols].apply(lambda r: [t for t in r if isinstance(t, str) and t.strip()], axis=1)
    rates = d["Hourly_Rate"].map(parse_rate_range)
    pay = d["Payment_type"].map({"Hourly": "hourly", "Fixed-price": "fixed"}).fillna("unknown")
    hires = pd.to_numeric(d["Freelancers_Num"], errors="coerce")
    out = pd.DataFrame(
        {
            "job_id": d["Job_URL"].map(job_id_from_url),
            "source": "ahmedmyalo_60k",
            "title": d["Job Title"],
            "description": d["Description"],
            "published_at": pd.NaT,  # only relative ages ("2 days ago") are available
            "pay_type": pay,
            "budget_usd": d["Job_Cost"].map(parse_money),
            "hourly_low": rates.map(lambda r: r[0]),
            "hourly_high": rates.map(lambda r: r[1]),
            "country": d["Client_Country"],
            "tags": tags,
            "experience_level": d["EX_level_demand"],
            "connects_old": d["Connects_Num"],
            "connects_new": d["New_Connects_Num"],
            "applicants": d["Applicants_Num"],
            "payment_verified": d["Payment_Situation"].map({"Payment verified": True,
                                                            "Payment unverified": False}),
            "client_spent_usd": d["Spent($)"],
            "client_rating": d["Rating"],
            "client_feedback_count": d["Feedback_Num"],
            "client_hires": hires,
        }
    )  # fmt: skip
    return out.reindex(columns=JOB_COLUMNS)


def load_200k() -> pd.DataFrame:
    frames = []
    for f in sorted(DS_200K.glob("*.csv")):
        d = pd.read_csv(f, low_memory=False)
        is_hourly = d["is_hourly"].map(to_bool)
        frames.append(
            pd.DataFrame(
                {
                    "job_id": d["link"].map(job_id_from_url),
                    "title": d["title"],
                    "published_at": pd.to_datetime(d["published_date"], utc=True, errors="coerce",
                                                   format="mixed"),
                    "pay_type": np.where(is_hourly.eq(True), "hourly",
                                         np.where(is_hourly.eq(False), "fixed", "unknown")),
                    "budget_usd": d["budget"],
                    "hourly_low": d["hourly_low"],
                    "hourly_high": d["hourly_high"],
                    "country": d["country"],
                }
            )
        )  # fmt: skip
    return pd.concat(frames, ignore_index=True)


# ----------------------------------------------------------------------------- cleaning


def clean_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Fill unknown pay types from which price exists, and null out impossible values."""
    df = df.copy()
    has_fixed = df["budget_usd"].notna() & (df["budget_usd"] > 0)
    has_hourly = df["hourly_low"].notna() | df["hourly_high"].notna()
    unknown = df["pay_type"].eq("unknown")
    df.loc[unknown & has_hourly & ~has_fixed, "pay_type"] = "hourly"
    df.loc[unknown & has_fixed & ~has_hourly, "pay_type"] = "fixed"
    # A fixed job's hourly fields (and vice versa) are noise.
    df.loc[df["pay_type"].eq("fixed"), ["hourly_low", "hourly_high"]] = np.nan
    df.loc[df["pay_type"].eq("hourly"), "budget_usd"] = np.nan
    bad_fixed = ~df["budget_usd"].between(FIXED_MIN, FIXED_MAX)
    df.loc[bad_fixed, "budget_usd"] = np.nan
    for col in ("hourly_low", "hourly_high"):
        df.loc[~df[col].between(HOURLY_MIN, HOURLY_MAX), col] = np.nan
    swap = df["hourly_low"] > df["hourly_high"]
    df.loc[swap, ["hourly_low", "hourly_high"]] = df.loc[swap, ["hourly_high", "hourly_low"]].values
    df["hourly_mid"] = [
        hourly_mid(lo, hi) for lo, hi in zip(df["hourly_low"], df["hourly_high"], strict=True)
    ]
    df["price_usd"] = np.where(df["pay_type"].eq("fixed"), df["budget_usd"], df["hourly_mid"])
    return df


def dedupe(df: pd.DataFrame, report: dict, key: str) -> pd.DataFrame:
    """Drop rows without an id, repeated ids, then near-duplicates (same normalised text)."""
    n0 = len(df)
    df = df[df["job_id"].notna()]
    n1 = len(df)
    df = df.sort_values(["job_id", "source"], kind="stable").drop_duplicates("job_id", keep="first")
    n2 = len(df)
    text = df["title"].map(norm_text) + "|" + df["description"].fillna("").map(norm_text).str[:300]
    df = df.assign(text_key=text.map(lambda t: hashlib.sha1(t.encode()).hexdigest()))
    df = df.drop_duplicates("text_key", keep="first")
    report[key] = {
        "rows_in": n0,
        "dropped_no_id": n0 - n1,
        "dropped_repeat_id": n1 - n2,
        "dropped_near_duplicate_text": n2 - len(df),
        "rows_out": len(df),
    }
    return df.drop(columns="text_key")


def build_corpus(tax: Taxonomy, report: dict) -> pd.DataFrame:
    j50, j60 = load_50k(), load_60k()
    report["loaded"] = {"asaniczka_50k": len(j50), "ahmedmyalo_60k": len(j60)}
    df = pd.concat([j60, j50], ignore_index=True)  # 60k first: richer rows win ties
    df = df[df["description"].notna() & df["title"].notna()]
    # Scraped text carries HTML entities (&quot; &amp; ...); decode them once here.
    df["title"] = df["title"].astype(str).map(html.unescape).str.strip()
    df["description"] = df["description"].astype(str).map(html.unescape).str.strip()
    df = dedupe(df, report, "corpus_dedupe")
    df = clean_prices(df)
    # Jobs without a stated price stay (common for real hourly posts); stats skip them.
    df["has_price"] = df["price_usd"].notna()

    text_skills = [
        tax.skills_in_text(f"{t} {d}") for t, d in zip(df["title"], df["description"], strict=True)
    ]
    tag_skills = [
        [tax.canon(t) for t in tags] if isinstance(tags, list) else [] for tags in df["tags"]
    ]
    df["skills"] = [
        list(dict.fromkeys(a + b)) for a, b in zip(tag_skills, text_skills, strict=True)
    ]
    df["skills_from_tags"] = [len(a) > 0 for a in tag_skills]
    df["category"] = [tax.category_of(s, t) for s, t in zip(df["skills"], df["title"], strict=True)]
    df["tags"] = df["tags"].map(lambda t: t if isinstance(t, list) else [])
    df = df.sort_values("job_id", kind="stable").reset_index(drop=True)
    report["corpus"] = {
        "rows": len(df),
        "by_source": df["source"].value_counts().sort_index().to_dict(),
        "by_pay_type": df["pay_type"].value_counts().sort_index().to_dict(),
        "by_category": df["category"].value_counts().sort_index().to_dict(),
        "share_with_any_skill": round(float((df["skills"].map(len) > 0).mean()), 4),
        "share_with_price": round(float(df["has_price"].mean()), 4),
    }
    return df


def train_title_classifier(corpus: pd.DataFrame) -> tuple[Pipeline, float]:
    """TF-IDF + logistic regression: title -> category. Deterministic (fixed split + solver)."""
    data = corpus[corpus["category"].ne(OTHER)]
    is_test = data["job_id"].map(lambda j: int(hashlib.sha1(j.encode()).hexdigest(), 16) % 5 == 0)
    clf = Pipeline(
        [
            ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True)),
            ("lr", LogisticRegression(max_iter=1000, C=4.0)),
        ]
    )
    clf.fit(data.loc[~is_test, "title"], data.loc[~is_test, "category"])
    acc = float((clf.predict(data.loc[is_test, "title"]) == data.loc[is_test, "category"]).mean())
    clf.fit(data["title"], data["category"])  # refit on everything for use
    return clf, round(acc, 4)


def build_price_frame(corpus: pd.DataFrame, tax: Taxonomy, report: dict) -> pd.DataFrame:
    """Corpus + 200k titles/prices (deduped by job id) for price statistics."""
    big = load_200k()
    report["loaded"]["asaniczka_200k"] = len(big)
    big = big[big["job_id"].notna()].drop_duplicates("job_id")
    big = big[~big["job_id"].isin(set(corpus["job_id"]))]
    big = clean_prices(big)
    big = big[big["price_usd"].notna()]
    big["skills"] = [tax.skills_in_text(t) for t in big["title"]]
    big["category"] = [
        tax.category_of(s, t) for s, t in zip(big["skills"], big["title"], strict=True)
    ]
    # Titles alone rarely name a seed skill, so fall back to a title classifier trained on the
    # corpus (where categories come from full text + tags). Only confident predictions are used.
    clf, holdout_acc = train_title_classifier(corpus)
    other = big["category"].eq(OTHER)
    if other.any():
        proba = clf.predict_proba(big.loc[other, "title"].fillna(""))
        best = proba.argmax(axis=1)
        conf = proba.max(axis=1)
        pred = np.where(conf >= TITLE_CLF_MIN_CONF, clf.classes_[best], OTHER)
        big.loc[other, "category"] = pred
    report["title_classifier"] = {
        "holdout_accuracy": holdout_acc,
        "min_confidence": TITLE_CLF_MIN_CONF,
        "reassigned_from_other": int((other & big["category"].ne(OTHER)).sum()),
    }
    report["pricing_rows_from_200k_not_in_corpus"] = len(big)
    cols = ["job_id", "pay_type", "price_usd", "skills", "category"]
    priced = corpus[corpus["has_price"]]
    return pd.concat([priced[cols], big[cols]], ignore_index=True)


def pricing_stats(prices: pd.DataFrame) -> pd.DataFrame:
    rows = []

    def add(group_type: str, group: str, pay_type: str, values: pd.Series) -> None:
        if len(values) < MIN_GROUP_N:
            return
        q = values.quantile(list(PCTS.values()))
        rows.append(
            {"group_type": group_type, "group": group, "pay_type": pay_type, "n": int(len(values)),
             **{k: round(float(v), 2) for k, v in zip(PCTS, q, strict=True)}}
        )  # fmt: skip

    for pay_type in ("fixed", "hourly"):
        sub = prices[prices["pay_type"] == pay_type]
        add("all", "all", pay_type, sub["price_usd"])
        for cat, g in sub.groupby("category", sort=True):
            add("category", str(cat), pay_type, g["price_usd"])
        exploded = sub[["skills", "price_usd"]].explode("skills").dropna(subset=["skills"])
        for skill, g in exploded.groupby("skills", sort=True):
            add("skill", str(skill), pay_type, g["price_usd"])
    return pd.DataFrame(rows).sort_values(["group_type", "group", "pay_type"], ignore_index=True)


def qtable(series: pd.Series) -> dict:
    s = pd.to_numeric(series, errors="coerce").dropna()
    return {
        "n": int(len(s)),
        "quantiles": [round(float(v), 4) for v in s.quantile(QUANTILES)] if len(s) else [],
    }


def share(series: pd.Series) -> dict:
    return series.value_counts(normalize=True).round(4).sort_index().to_dict()


def client_priors(report: dict) -> dict:
    c = pd.read_csv(DS_CONTRACTS / "contracts.csv", low_memory=False)
    report["loaded"]["contracts"] = len(c)
    start = pd.to_datetime(c["start_date"], errors="coerce", format="mixed")
    end = pd.to_datetime(c["end_date"], errors="coerce", format="mixed")
    days = (end - start).dt.total_seconds() / 86400
    j = load_60k()
    countries = pd.concat([load_50k()["country"], j["country"]]).dropna()
    return {
        "note": "Quantile tables at q=0.00,0.05,...,1.00 for sampling synthetic clients. "
        "Contracts carry no client id, so these are per-contract / per-job distributions.",
        "quantile_levels": QUANTILES,
        "contracts": {
            "total_paid_usd": qtable(c["total_paid"]),
            "hourly_rate_usd": qtable(c["hourly_rate"]),
            "total_hours": qtable(c.loc[c["hourly_rate"].notna(), "total_hours"]),
            "duration_days": qtable(days[days >= 0]),
            "share_hourly": round(float(c["hourly_rate"].notna().mean()), 4),
            "share_ongoing": round(float(c["end_date"].isna().mean()), 4),
        },
        "jobs_60k": {
            "client_spent_usd": qtable(j["client_spent_usd"]),
            "share_spent_zero": round(float((j["client_spent_usd"] == 0).mean()), 4),
            "client_rating": qtable(j["client_rating"]),
            "share_rating_missing": round(float(j["client_rating"].isna().mean()), 4),
            "client_feedback_count": qtable(j["client_feedback_count"]),
            "client_hires": qtable(j["client_hires"]),
            "share_payment_verified": round(float(j["payment_verified"].eq(True).mean()), 4),
            "applicants": share(j["applicants"]),
            "experience_level": share(j["experience_level"]),
            "connects_old": share(j["connects_old"].dropna().astype(int).astype(str)),
            "connects_new_over_old": round(float((j["connects_new"] / j["connects_old"]).median()), 2),  # noqa: E501
        },
        "country_share_top30": countries.value_counts(normalize=True).head(30).round(4).to_dict(),
    }  # fmt: skip


def freelancer_priors(report: dict) -> dict:
    f = pd.read_csv(DS_FREELANCERS / "freelancer_gig_success_dataset.csv", low_memory=False)
    report["loaded"]["freelancers"] = len(f)
    by_skill = {}
    for skill, g in f.groupby("primary_skill", sort=True):
        by_skill[str(skill)] = {
            "hourly_rate_usd": qtable(g["hourly_rate_usd"]),
            "job_success_rate": qtable(g["job_success_rate"]),
            "years_experience": qtable(g["years_experience"]),
        }
    return {
        "note": "Source appears synthetic itself (see DATA_CARD). Used only as weak priors.",
        "quantile_levels": QUANTILES,
        "by_primary_skill": by_skill,
    }


# ----------------------------------------------------------------------------- outputs


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(
        json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    missing = [
        p.name for p in (DS_50K, DS_60K, DS_200K, DS_CONTRACTS, DS_FREELANCERS) if not p.exists()
    ]
    if missing:
        print(f"missing raw datasets: {missing}; run scripts/download_kaggle.sh", file=sys.stderr)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {}

    print("taxonomy ...", flush=True)
    raw60 = load_60k()
    tag_counts = Counter(t for tags in raw60["tags"] for t in tags)
    tax = Taxonomy(load_seed(), tag_counts)
    tagged = raw60[raw60["tags"].map(len) > 0].dropna(subset=["title", "description"])
    refined = tax.refine(
        list(tagged["title"]),
        [f"{t} {d}" for t, d in zip(tagged["title"], tagged["description"], strict=True)],
        list(tagged["tags"]),
    )
    report["taxonomy"] = {
        "raw_unique_tags": len(tag_counts),
        "vocab_size": len(tax.vocab),
        "seed_category_skills": len(tax.skill_category) - len(tax.learned),
        **refined,
    }

    print("corpus ...", flush=True)
    corpus = build_corpus(tax, report)
    print("pricing ...", flush=True)
    stats = pricing_stats(build_price_frame(corpus, tax, report))
    report["pricing_stats_rows"] = len(stats)
    print("priors ...", flush=True)
    clients = client_priors(report)
    freelancers = freelancer_priors(report)

    outputs = {
        "jobs_corpus.parquet": lambda p: corpus.to_parquet(p, index=False),
        "pricing_stats.parquet": lambda p: stats.to_parquet(p, index=False),
        "skill_taxonomy.json": lambda p: _write_json(p, tax.to_json()),
        "client_priors.json": lambda p: _write_json(p, clients),
        "freelancer_priors.json": lambda p: _write_json(p, freelancers),
        "preprocess_report.json": lambda p: _write_json(p, report),
    }
    for name, write in outputs.items():
        write(OUT / name)
    _write_json(OUT / "MANIFEST.json", {name: sha256(OUT / name) for name in sorted(outputs)})
    print(json.dumps(report["corpus"], indent=2))
    print(f"wrote {len(outputs)} files + MANIFEST.json to {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
