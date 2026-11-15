# ADR 0002: Synthetic data, gold labels by construction, deterministic seeding

- Status: accepted
- Date: 2026-11-15

## Context
The assignment's "provided" GigSim, personas, policy pack and dev set do not exist; we build them
from Kaggle data plus synthetic data. If an LLM produced both the data and its labels, evaluation
would grade the generator against itself.

## Decisions
1. **Gold labels come from construction.** Dev/test jobs are written *from* chosen portfolio
   projects (gold evidence), planted scams/injections, a written bid/skip rule applied to the
   constructed job, and real Kaggle price percentiles. Details: `docs/DATA_CARD.md` section 3.
2. **No LLM in `make seed`.** Wording comes from seeded templates plus hand-written persona facts
   (`data/generators/persona_specs.yaml`). This keeps the seed deterministic, free and runnable in CI
   without API keys. LLM paraphrasing may be added later as an optional, separately versioned step.
3. **Provenance = generator file's git blob sha** (`<generator>@<sha12>`), not the commit sha, so
   committing does not change the bytes of already-generated data, and any change to a generator is
   visible in every record it produced.
4. **Determinism:** `random.Random("<seed>:<name>")` per generator, time pinned to a reference date,
   sorted JSON keys, LF line endings. `MANIFEST.json` files hold sha256 of every output; two runs of
   `make seed` must produce identical manifests.
5. **Held-out test set** (`data/heldout/`, 100 jobs per persona) is git-ignored and never used for
   tuning; it stands in for the instructor's hidden set.
6. **trial-1 (licence unknown)** is not loaded; its fraud labels only inspired scam patterns.

## Consequences
- Gold labels are reproducible and explainable in the viva ("how was this label produced?").
- Templates make text less varied than real writing; RAG results may be optimistic on wording
  variety. Mitigation: synonyms, implied phrasing, repeated archetypes across industries, real job
  text in the GigSim stream. Reported as a limitation.
