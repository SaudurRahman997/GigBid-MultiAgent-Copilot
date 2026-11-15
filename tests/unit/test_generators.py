"""Tests for the synthetic-data generators. Everything is generated into tmp_path."""

import hashlib
import json
import random
from pathlib import Path

import pytest

from data.generators import clients, common, devset, jobs, personas, proposals, validate
from data.generators.common import read_jsonl, write_jsonl


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """Personas + proposals + clients + dev/test sets in a temp dir (no Kaggle data needed)."""
    root = tmp_path_factory.mktemp("world")
    p_root, dev_root, held_root = root / "personas", root / "devset", root / "heldout"
    for pid, spec in common.specs()["personas"].items():
        personas.generate_persona(pid, spec, p_root)
        proposals.generate_for(pid, spec, p_root)
    clients.generate(root / "clients.jsonl")
    summary = devset.generate(p_root, dev_root, held_root, root / "clients.jsonl")
    return {
        "root": root,
        "personas": p_root,
        "dev": dev_root,
        "held": held_root,
        "summary": summary,
    }


def _hash_tree(root: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        h.update(f.relative_to(root).as_posix().encode() + f.read_bytes())
    return h.hexdigest()


# ----------------------------------------------------------------------------- common


def test_provenance_is_generator_at_blob_sha():
    prov = common.provenance(personas.__file__)
    name, sha = prov.split("@")
    assert name == "personas" and len(sha) == 12


def test_jsonl_roundtrip_survives_unicode_line_separators(tmp_path):
    recs = [{"text": "line separator and \x85 next-line"}, {"text": "ok"}]
    write_jsonl(tmp_path / "x.jsonl", recs)
    assert read_jsonl(tmp_path / "x.jsonl") == recs


def test_sample_quantile_stays_in_range():
    table = {"quantiles": [0, 10, 20, 30, 40]}
    levels = [0, 0.25, 0.5, 0.75, 1.0]
    r = random.Random(1)
    vals = [common.sample_quantile(table, levels, r) for _ in range(500)]
    assert min(vals) >= 0 and max(vals) <= 40
    assert 15 < sum(vals) / len(vals) < 25


@pytest.mark.parametrize(
    ("pay", "budget", "hourly", "expected"),
    [("fixed", 30, None, 4), ("fixed", 150, None, 8), ("fixed", 999, None, 12),
     ("fixed", 5000, None, 16), ("hourly", None, 15, 4), ("hourly", None, 80, 16),
     ("fixed", None, None, 8)],
)  # fmt: skip
def test_connects_cost_tiers(pay, budget, hourly, expected):
    assert common.connects_cost(pay, budget, hourly) == expected


# ----------------------------------------------------------------------------- personas


def test_persona_corpus_sizes_and_stamps(world):
    for pid in common.specs()["personas"]:
        ev = read_jsonl(world["personas"] / pid / "evidence.jsonl")
        types = [e["type"] for e in ev]
        assert 15 <= types.count("case_study") <= 25
        assert 20 <= types.count("review") <= 40
        assert 5 <= types.count("readme") <= 8
        assert types.count("cv") == 1
        assert all(e["synthetic"] is True and e["provenance"] for e in ev)
        assert (world["personas"] / pid / "cv.pdf").read_bytes().startswith(b"%PDF")


def test_case_studies_often_imply_skills_without_naming_them(world):
    ev = read_jsonl(world["personas"] / "ai_ml" / "evidence.jsonl")
    cases = [e for e in ev if e["type"] == "case_study"]
    implied_only = [e for e in cases if not e["skills_named"]]
    assert implied_only, "some case studies must not list their stack"
    assert len(implied_only) < len(cases), "some case studies must list their stack"


def test_persona_generation_is_deterministic(tmp_path):
    spec = common.specs()["personas"]["data_analyst"]
    personas.generate_persona("data_analyst", spec, tmp_path / "a")
    personas.generate_persona("data_analyst", spec, tmp_path / "b")
    assert _hash_tree(tmp_path / "a") == _hash_tree(tmp_path / "b")


# ----------------------------------------------------------------------------- clients


def _client(**kw):
    base = {"rating": 4.9, "jobs_posted": 10, "hire_rate": 0.6, "payment_verified": True,
            "total_spent_usd": 5000.0}  # fmt: skip
    return {**base, **kw}


@pytest.mark.parametrize(
    ("kw", "expected"),
    [({}, "good"), ({"rating": 3.5}, "poor"), ({"hire_rate": 0.1}, "poor"),
     ({"payment_verified": False, "total_spent_usd": 0.0, "rating": None}, "poor"),
     ({"total_spent_usd": 200.0}, "ok"), ({"jobs_posted": 3, "hire_rate": 0.0, "rating": None,
                                           "total_spent_usd": 0.0}, "ok")],
)  # fmt: skip
def test_history_quality_rule(kw, expected):
    assert clients.history_quality(_client(**kw)) == expected


def test_clients_have_hidden_preferences(world):
    cs = read_jsonl(world["root"] / "clients.jsonl")
    assert len(cs) == clients.N_CLIENTS
    assert all(
        {"budget_ceiling_multiplier", "dislikes_generic_opening"} <= set(c["_hidden"]) for c in cs
    )
    assert {c["_gold"]["history_quality"] for c in cs} == {"good", "ok", "poor"}


# ----------------------------------------------------------------------------- proposals


def test_planted_features_drive_outcomes():
    r = random.Random(7)

    def reply_rate(specific, personal, position):
        outs = [proposals.outcome(specific, personal, position, r)[0] for _ in range(3000)]
        return sum(o != "ignored" for o in outs) / len(outs)

    best, worst = reply_rate(True, True, "within"), reply_rate(False, False, "above")
    assert best > 0.6 and worst < 0.15
    assert reply_rate(True, False, "within") > reply_rate(False, False, "within")
    assert reply_rate(False, True, "within") > reply_rate(False, False, "within")


def test_proposals_written_with_outcomes(world):
    props = read_jsonl(world["personas"] / "fullstack" / "proposals.jsonl")
    assert len(props) == proposals.N_PER_PERSONA
    assert {p["outcome"] for p in props} == {"won", "replied", "ignored"}


# ----------------------------------------------------------------------------- jobs


def _real_job():
    return {"job_id": "gs_00001", "source_job_id": "abc", "title": "Need React Developer",
            "description": "We build apps. Need a dashboard. Must know React. Budget is fixed. Start soon.",
            "pay_type": "fixed", "budget_usd": 500.0, "hourly_low": None, "hourly_high": None,
            "synthetic": False, "provenance": "kaggle:x", "licence": "ODC-By",
            "_gold": {"kind": "real", "is_scam": False, "scam_type": None, "has_injection": False,
                      "risk_flags": [], "dup_of": None}}  # fmt: skip


def test_inject_plants_instruction_and_marks_synthetic():
    out = jobs.inject(_real_job(), random.Random(0))
    assert out["_gold"]["has_injection"] and out["_gold"]["injection_text"] in out["description"]
    assert out["synthetic"] is True and "licence" not in out and out["derived_from"] == "abc"


def test_duplicate_points_to_original_with_small_edits():
    orig = _real_job()
    dup = jobs.duplicate(orig, random.Random(3))
    assert dup["_gold"]["dup_of"] == "gs_00001" and "duplicate" in dup["_gold"]["risk_flags"]
    assert dup["title"] != orig["title"] or dup["description"] != orig["description"]
    assert 450 <= dup["budget_usd"] <= 550


def test_scam_jobs_carry_type_and_flags():
    r = random.Random(5)
    for _ in range(20):
        j = jobs.scam_job(r)
        assert j["_gold"]["is_scam"] and j["_gold"]["scam_type"] in jobs.SCAMS
        assert j["_gold"]["risk_flags"] and j["description"][0].isupper()


# ----------------------------------------------------------------------------- devset


@pytest.mark.parametrize(
    ("job", "quality", "scam", "expected"),
    [
        ({"pay_type": "fixed", "budget_usd": 500, "requirements": [{"skill": "sql", "must_have": True}]},
         "ok", False, ("bid", None)),
        ({"pay_type": "fixed", "budget_usd": 500, "requirements": []}, "ok", True, ("skip", "scam")),
        ({"pay_type": "fixed", "budget_usd": 500, "requirements": [{"skill": "unity", "must_have": True}]},
         "ok", False, ("skip", "missing_skill")),
        ({"pay_type": "fixed", "budget_usd": 500, "requirements": [{"skill": "unity", "must_have": False}]},
         "ok", False, ("bid", None)),
        ({"pay_type": "fixed", "budget_usd": 100, "requirements": []}, "ok", False, ("skip", "low_budget")),
        ({"pay_type": "hourly", "hourly_high": 15, "requirements": []}, "ok", False, ("skip", "low_budget")),
        ({"pay_type": "fixed", "budget_usd": 500, "requirements": []}, "poor", False, ("skip", "poor_client")),
    ],
)  # fmt: skip
def test_bid_rule(job, quality, scam, expected):
    assert devset.bid_rule(job, {"sql"}, {"fixed": 200, "hourly": 25}, quality, scam) == expected


def test_devset_sizes_and_gold_by_construction(world):
    for pid, s in world["summary"].items():
        assert s["dev"] == devset.N_DEV and s["test"] == devset.N_PER_PERSONA - devset.N_DEV
        dev = read_jsonl(world["dev"] / f"{pid}.jsonl")
        evidence = {e["id"]: e for e in read_jsonl(world["personas"] / pid / "evidence.jsonl")}
        for j in dev:
            g = j["_gold"]
            if g["anchor_project_ids"]:
                assert 2 <= len(g["evidence_ids"]) <= 5
                # every gold item belongs to an anchor project
                assert {evidence[e]["project_id"] for e in g["evidence_ids"]} <= set(
                    g["anchor_project_ids"]
                )
            if g["is_scam"]:
                assert g["bid"] == "skip" and g["skip_reason"] == "scam" and not g["evidence_ids"]
            assert g["price_band"]["low"] <= g["price_band"]["high"]


def test_dev_and_test_ids_are_disjoint(world):
    for pid in world["summary"]:
        dev = {j["job_id"] for j in read_jsonl(world["dev"] / f"{pid}.jsonl")}
        test = {j["job_id"] for j in read_jsonl(world["held"] / f"{pid}.jsonl")}
        assert dev and test and not dev & test


def test_validator_accepts_generated_devset(world):
    errors: list[str] = []
    out = validate.check_devset(errors, world["dev"], world["personas"])
    assert not errors and set(out) == set(world["summary"])


def test_validator_flags_missing_provenance(tmp_path):
    write_jsonl(tmp_path / "bad.jsonl", [{"synthetic": True}, {"provenance": "x"},
                                         {"synthetic": False, "provenance": "kaggle:y"}])  # fmt: skip
    errors: list[str] = []
    validate.check_files([tmp_path], errors)
    assert len(errors) == 3


def test_policy_pack_parses():
    pol = common.policy()
    ids = {r["id"] for r in pol["rules"]}
    assert {"no_off_platform_contact", "no_guarantees", "no_external_links"} <= ids
    assert json.dumps(pol["connects"]["tiers"]["fixed"][-1]["below"]) == "Infinity"
