"""Unit tests for data/generators/preprocess.py on tiny hand-made inputs (no Kaggle data)."""

from collections import Counter

import numpy as np
import pandas as pd
import pytest

import data.generators.preprocess as pp

SEED = {
    "categories": {
        "ai_ml": {"label": "AI", "skills": ["machine learning", "pytorch", "openai api"]},
        "web_dev": {"label": "Web", "skills": ["react", "node.js", "web development"]},
    },
    "aliases": {
        "reactjs": "react",
        "nodejs": "node.js",
        "ml": "machine learning",
        "openai": "openai api",
    },
    "text_stoplist": ["ml"],
}


@pytest.fixture
def tax():
    return pp.Taxonomy(SEED, Counter({"React": 40, "Magento": 20, "Rare Tag": 2}))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$2,500 ", 2500.0),
        ("$1.5k", 1500.0),
        ("0", 0.0),
        ("40", 40.0),
        (np.nan, None),
        ("n/a", None),
    ],
)
def test_parse_money(raw, expected):
    assert pp.parse_money(raw) == expected


def test_parse_rate_range():
    assert pp.parse_rate_range("$10.00-$45.00") == (10.0, 45.0)
    assert pp.parse_rate_range("$20") == (20.0, None)
    assert pp.parse_rate_range(np.nan) == (None, None)


def test_job_id_from_url_handles_both_encodings():
    assert pp.job_id_from_url("https://www.upwork.com/jobs/X_%7E0173dd044736aa?source=rss") == (
        "0173dd044736aa"
    )
    assert pp.job_id_from_url("https://www.upwork.com/jobs/Y_~01ed2a6e0ad5dd7a3c/") == (
        "01ed2a6e0ad5dd7a3c"
    )
    assert pp.job_id_from_url("https://example.com") is None


def test_vocab_keeps_frequent_tags_and_seed_skills(tax):
    assert {"react", "magento", "pytorch"} <= tax.vocab
    assert "rare tag" not in tax.vocab


def test_skills_in_text_uses_aliases_ngrams_and_stoplist(tax):
    found = tax.skills_in_text("Need a ReactJS + Node.js dev; ML ok. Web development, OpenAI.")
    assert found == ["react", "node.js", "web development", "openai api"]
    assert "machine learning" not in found  # "ml" is stoplisted for free text


def test_category_of_counts_skills_and_breaks_ties_by_seed_order(tax):
    assert tax.category_of(["react", "node.js"]) == "web_dev"
    assert tax.category_of(["pytorch", "react"]) == "ai_ml"  # tie -> first category in seed
    assert tax.category_of(["react"], title="PyTorch model with OpenAI") == "ai_ml"  # title x2
    assert tax.category_of(["unknown"]) == pp.OTHER


def test_refine_learns_category_and_drops_generic_words(monkeypatch, tax):
    monkeypatch.setattr(pp, "TEXT_MIN_N", 3)
    monkeypatch.setattr(pp, "LEARN_MIN_N", 3)
    titles = ["React shop"] * 4
    texts = ["React magento store build"] * 4
    tags = [["React", "Magento"]] * 4
    out = tax.refine(titles, texts, tags)
    assert tax.skill_category["magento"] == "web_dev"  # learned from co-occurrence
    assert out["learned_category_skills"] >= 1
    # "magento" is always tagged when mentioned -> precise -> kept for text matching
    assert "magento" in tax.skills_in_text("magento migration")


def test_clean_prices_fills_pay_type_and_nulls_bad_values():
    df = pd.DataFrame(
        {
            "pay_type": ["unknown", "unknown", "fixed", "hourly", "hourly"],
            "budget_usd": [500.0, np.nan, 2.0, 100.0, np.nan],
            "hourly_low": [np.nan, 20.0, 10.0, 40.0, 900.0],
            "hourly_high": [np.nan, 40.0, 30.0, 30.0, np.nan],
        }
    )
    out = pp.clean_prices(df)
    assert list(out["pay_type"]) == ["fixed", "hourly", "fixed", "hourly", "hourly"]
    assert out.loc[0, "price_usd"] == 500.0
    assert out.loc[1, "price_usd"] == 30.0  # midpoint
    assert np.isnan(out.loc[2, "price_usd"])  # $2 fixed is below FIXED_MIN
    assert (out.loc[3, "hourly_low"], out.loc[3, "hourly_high"]) == (30.0, 40.0)  # swapped
    assert np.isnan(out.loc[3, "budget_usd"])  # hourly job's budget is noise
    assert np.isnan(out.loc[4, "price_usd"])  # $900/h is above HOURLY_MAX


def test_dedupe_by_id_then_near_duplicate_text():
    df = pd.DataFrame(
        {
            "job_id": ["a", "a", "b", "c", None],
            "source": ["s"] * 5,
            "title": ["Build API", "Build API", "Build  API!", "Logo", "x"],
            "description": ["Need FastAPI", "Need FastAPI", "need fastapi", "Design a logo", "y"],
        }
    )
    report: dict = {}
    out = pp.dedupe(df, report, "k")
    assert sorted(out["job_id"]) == ["a", "c"]
    assert report["k"] == {
        "rows_in": 5,
        "dropped_no_id": 1,
        "dropped_repeat_id": 1,
        "dropped_near_duplicate_text": 1,
        "rows_out": 2,
    }


def test_pricing_stats_percentiles_and_min_group(monkeypatch):
    monkeypatch.setattr(pp, "MIN_GROUP_N", 5)
    prices = pd.DataFrame(
        {
            "job_id": [str(i) for i in range(12)],
            "pay_type": ["fixed"] * 10 + ["hourly"] * 2,
            "price_usd": [float(v) for v in range(10, 110, 10)] + [20.0, 30.0],
            "skills": [["react"]] * 10 + [["react"]] * 2,
            "category": ["web_dev"] * 12,
        }
    )
    stats = pp.pricing_stats(prices)
    row = stats[(stats.group_type == "category") & (stats.pay_type == "fixed")].iloc[0]
    assert row["n"] == 10 and row["p50"] == 55.0 and row["p25"] == 32.5 and row["p75"] == 77.5
    assert stats[stats.pay_type == "hourly"].empty  # only 2 rows < MIN_GROUP_N


def test_qtable_shape():
    q = pp.qtable(pd.Series([1, 2, 3, None]))
    assert q["n"] == 3 and len(q["quantiles"]) == len(pp.QUANTILES)
    assert q["quantiles"][0] == 1 and q["quantiles"][-1] == 3
