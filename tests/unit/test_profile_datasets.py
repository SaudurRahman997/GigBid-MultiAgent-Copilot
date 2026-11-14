"""Profiler tests on tiny synthetic tables (no Kaggle data needed)."""

import pandas as pd

import data.generators.profile_datasets as prof


def test_profile_table_reports_rows_nulls_and_samples(tmp_path):
    f = tmp_path / "t.csv"
    pd.DataFrame({"a": [1, 2, None, 4], "b": ["x", "y", "y", None]}).to_csv(f, index=False)
    md = prof.profile_table(f)
    assert "rows: **4**" in md
    assert "| `a` | float64 | 25.0 | 3 |" in md
    assert "| `b` | " in md and "| 25.0 | 2 |" in md
    assert "5 sample rows" in md


def test_job_ids_handle_encoded_and_literal_tilde(tmp_path, monkeypatch):
    monkeypatch.setattr(prof, "RAW", tmp_path)
    (tmp_path / "ds").mkdir()
    pd.DataFrame(
        {
            "link": [
                "https://www.upwork.com/jobs/A_%7E0173dd044736aa?source=rss",
                "https://www.upwork.com/jobs/B_~01ed2a6e0ad5dd7a3c/",
                "https://example.com/no-id",
            ]
        }
    ).to_csv(tmp_path / "ds" / "j.csv", index=False)
    assert prof._job_ids("ds", "link") == {"0173dd044736aa", "01ed2a6e0ad5dd7a3c"}
