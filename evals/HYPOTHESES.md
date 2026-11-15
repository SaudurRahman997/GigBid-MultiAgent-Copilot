# R&D B hypotheses (written BEFORE running the variants)

> Drafted on 2026-11-15 before any variant was evaluated. **Edit these in your own words** -
> the report must compare results against what you expected. Do not change them after seeing
> numbers; add a dated "Revisions" note instead.

Setup the predictions refer to: dev set, ~150 jobs with gold evidence per persona, gold = the
2-5 evidence items of the 1-2 projects each job was written from; requirements are phrased by
name (~60%), by synonym (~17%) or only implied (~22%). Corpus per persona: ~55 evidence items +
150 past proposals (never gold, but they compete in retrieval).

| ID | Hypothesis | Measured by | Would be refuted if |
|---|---|---|---|
| H1 | **V0 (whole post, fixed chunks) is the weakest.** One embedding of a multi-requirement post blurs the requirements, and fixed windows cut case studies mid-story. | Recall@5, MRR | V0 is within 0.02 Recall@5 of V1 |
| H2 | **Decomposition (V1) beats V0, most on two-project jobs**, because each requirement gets its own query and the second project is not drowned out. | Recall@5 overall and on `two_anchor_projects` | V1 gain on two-anchor jobs is not larger than on one-anchor jobs |
| H3 | **Hybrid (V2) beats V1 when skills are named exactly** (BM25 matches "Power BI", "LangChain"), but adds little or hurts on implied requirements, where only dense similarity can help. | Recall@5 on `names_every_skill` vs `has_implied_requirement` | V2's gain is equal or larger on implied requirements |
| H4 | **Reranking (V3) improves MRR more than Recall@5**: the cross-encoder mostly reorders a candidate set that already contains the gold. | delta MRR vs delta Recall@5 (V3 - V2) | delta Recall@5 >= delta MRR |
| H5 | **Outcome-aware ranking (V4) does not improve retrieval metrics** (gold is defined by topical fit, not outcome) and may lower them by boosting won proposals, which are never gold. It is expected to matter for GigSim reply rate instead. | Recall@5/MRR vs V3; GigSim reply rate (gigsim_outcomes.py) | V4 raises Recall@5 by > 0.02 |
| H6 | **Corrective RAG (V8) refuses on most missing-skill jobs** (no supporting evidence exists) while rarely refusing jobs that do have gold evidence. | correct_refusal_rate on no-evidence jobs; refused_with_gold | correct refusal < 0.5 or refused_with_gold > 0.1 |

**Predicted order on Recall@5:** V0 < V1 < V2 <= V3 ~ V8 (V4 slightly below V3).

**Where better retrieval may NOT raise reply rate (to check in gigsim_outcomes.py):** the simulated
client rewards must-have skill *mentions*, specificity and price - a proposal can mention the
skill from a weaker piece of evidence and still get a reply, so beyond a point Recall@5 gains
should stop paying off.

## Revisions
- **2026-11-15, after the V0/V2 checkpoint run (hypotheses above unchanged):** added the metric
  `project_recall@5` (share of a job's anchor projects with at least one evidence item in the
  top 5). Reason: the checkpoint showed past proposals filling about half of the top-5 slots and
  client reviews (45% of gold items, outcome-focused by design) rarely retrieved, so strict
  Recall@5 over 3-4 gold items understates whether the *right project* was found. Gold labels
  were not changed. H1-H6 are evaluated on the original metrics; project recall is reported
  alongside.
