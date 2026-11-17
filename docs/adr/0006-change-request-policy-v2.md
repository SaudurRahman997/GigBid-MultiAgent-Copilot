# ADR 0006: Change request — platform policy v2

Status: accepted (2026-11-17)

## Context

BUILD_SPEC section 9 simulates a platform policy update with `gigsim/policy/v2.yaml`:

1. Connects cost doubles for jobs with more than 20 proposals (`multiplier_if_applicants_over_20: 2`,
   cap per proposal 16 -> 32).
2. Proposals may not include external links (`external_links_allowed: false`).

GigBid must absorb it by editing only `agent/config.yaml`, `data/policy_pack/` and at most one prompt.

## Preparation (before the change request, separate commit `2082a71`)

The pricing node used the job's base Connects cost, so it could not see a busy-job multiplier.
It now computes the cost from the policy pack's `connects` rules (`default`, `busy_applicants`,
`busy_multiplier`, `max_per_proposal`). With the v1 values the behaviour is unchanged (all tests
passed before and after). `tests/unit/test_policy_alignment.py` checks that the agent's policy pack
matches the platform policy named by `agent/config.yaml` `policy_version` (version, Connects rules,
link rule), so a future platform update fails CI until the pack absorbs it.

This preparation was a code change and was not timed. The change request itself was data-only.

## The change (commit after this ADR's first draft)

| File | Change |
|---|---|
| `agent/config.yaml` | `policy_version: v1` -> `v2` |
| `data/policy_pack/policy.yaml` | `version` v2, provenance v2, `no_external_links` severity `warn` -> `block`, `connects.max_per_proposal` 16 -> 32, `connects.busy_multiplier` 1 -> 2 |
| `data/policy_pack/policy.md` | `no_external_links` row: warn -> block |

No prompt and no Python file changed.

## Measurement

- Diff size: **3 files, 7 insertions, 7 deletions** (`git diff --stat`).
- Time: **2 min 1 s**, from the first edit (2026-11-17T12:25:51Z) to the full test suite green
  (2026-11-17T12:27:52Z; 200 passed).
- Effect: a letter containing a link is now blocked by Compliance before approval instead of only
  warned (covered by `test_link_in_a_letter_follows_the_pack`), and the pricing node's Connects cost
  and the approval preview double on busy jobs, capped at 32 (`test_connects_cost_rule`).

## Consequences

- Rules that a platform can change live in data, and a test ties them to the platform version.
- The dev set has no applicant counts, so the busy-job rule does not move dev-set decision metrics;
  it is covered by unit tests.
