"""The agent's policy pack must match the platform policy it targets (BUILD_SPEC section 9).

agent/config.yaml `policy_version` names the GigSim platform policy (gigsim/policy/<version>.yaml).
If the platform changes its rules, these tests fail until data/policy_pack/ is updated to absorb it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from agent.handoffs import Budget, JobSpec
from agent.marketplace_port import load_config
from agent.nodes.proposal import check_compliance, connects_cost
from agent.runtime import Deps

ROOT = Path(__file__).resolve().parents[2]


def platform() -> dict:
    return yaml.safe_load(
        (ROOT / "gigsim" / "policy" / f"{load_config()['policy_version']}.yaml").read_text(
            encoding="utf-8"
        )
    )


def pack() -> dict:
    return Deps(mcp=None, config={}, user="").policy


def spec(applicants: str | None, connects: int | None = 12) -> JobSpec:
    return JobSpec(job_id="j", title="t", requirements=[], budget=Budget(pay_type="fixed", amount=500),
                   connects_required=connects, applicants=applicants)  # fmt: skip


def test_pack_version_matches_platform_version():
    assert pack()["version"] == load_config()["policy_version"] == platform()["version"]


def test_connects_rules_match_the_platform():
    p, c = platform()["connects"], pack()["connects"]
    assert c["busy_multiplier"] == p["multiplier_if_applicants_over_20"]
    assert c["max_per_proposal"] == p["max_per_proposal"]


def test_link_rule_matches_the_platform():
    rule = next(r for r in pack()["rules"] if r["id"] == "no_external_links")
    assert (rule["severity"] == "block") == (not platform()["proposals"]["external_links_allowed"])


def test_connects_cost_rule():
    v1 = {
        "default": 8,
        "max_per_proposal": 16,
        "busy_applicants": ["20 to 50", "50+"],
        "busy_multiplier": 1,
    }
    v2 = {**v1, "max_per_proposal": 32, "busy_multiplier": 2}
    assert connects_cost(spec("50+"), v1) == 12
    assert connects_cost(spec("50+"), v2) == 24
    assert connects_cost(spec("5 to 10"), v2) == 12
    assert connects_cost(spec(None, None), v2) == 8
    assert (
        connects_cost(spec("50+", 16), v2) == 32 and connects_cost(spec("50+", 20), v2) == 32
    )  # capped


def test_link_in_a_letter_follows_the_pack():
    verdict = check_compliance("See my work at https://example.com/portfolio", pack(), [])
    blocked = "no_external_links:link" in verdict.violations
    assert blocked == (not platform()["proposals"]["external_links_allowed"])
