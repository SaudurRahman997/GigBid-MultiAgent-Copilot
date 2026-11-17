# Extension X2: proposal experiments (A/B test of two proposal strategies)

Source: `evals/results/extension/ab.json` and per-job letters and outcomes in `ab.jobs.jsonl`,
written by `evals/runners/extension_ab.py`.

## Question

Does opening a proposal with a quantified past result get more client replies than opening by
restating the client's need?

## Arms

The two arms are switchable with `writer.strategy` in `agent/config.yaml`. Everything else is
identical: graph, decision, price, evidence retrieval, claim verification, compliance.

| Arm | `writer.strategy` | Letter shape |
|---|---|---|
| A (current default) | `evidence_first` | restated need -> 3 cited evidence sentences -> must-have skills -> price |
| B | `outcome_first` | the most relevant cited evidence sentence that contains a number (years excluded) -> restated need -> 2 more cited evidence sentences -> skills -> price -> one scoping question ("Which matters most to you first: X, or Y?") |

Both arms cite every evidence sentence and pass the same Compliance filter
(`tests/unit/test_extension.py`).

## Design

- **Population:** all 600 dev jobs (3 personas). Each job runs through the real bid graph (rules
  mode, in-process tools) once per arm, up to the approval interrupt. The 267 jobs where the graph
  bids form the sample; the decision does not depend on the writer, so both arms bid on the same jobs.
- **Paired:** each arm's letters go to a fresh in-process GigSim world with the same seed and chaos
  off, and simulated time advances 30 days. The two worlds are identical, so the same job meets the
  same simulated client with the same hidden preferences; only the letter differs.
- **Primary test:** two-sided exact McNemar test on the discordant pairs. Reported alongside: a
  two-proportion z-test and a 95% CI on the paired difference. Hypothesis and test were fixed before
  the full run: B > A on reply rate.

## Results

| | A `evidence_first` | B `outcome_first` |
|---|---|---|
| Pairs | 267 | 267 |
| Reply rate (replied, interview or hired) | 0.446 | 0.513 |
| Interview rate | 0.236 | 0.292 |

- Difference B - A: **+0.067**, 95% CI **[-0.009, +0.144]**.
- Discordant pairs: A replied and B did not on 46 jobs; B replied and A did not on 64.
- **McNemar exact p = 0.105**; two-proportion z = 1.56, p = 0.119.

By persona:

| Persona | Pairs | A | B |
|---|---|---|---|
| ai_ml | 89 | 0.483 | 0.506 |
| fullstack | 101 | 0.386 | 0.545 |
| data_analyst | 77 | 0.481 | 0.481 |

## Conclusion

B is ahead on reply rate (+6.7 points) and interview rate (+5.6 points), but the difference is
**not significant at the 5% level** (p = 0.105). The CI includes zero. The gain is concentrated in
the fullstack persona; data_analyst shows no difference.

Decision: the default stays `evidence_first`. `outcome_first` is available as a config option, and
the next step is a larger sample (the held-out job set, or more simulated jobs) to confirm or reject
the fullstack effect.

## Threats to validity

- Outcomes come from GigSim's simulated clients, not real clients. GigSim scores "specific evidence
  with numbers" over the whole letter, not by position, so B's advantage is not just a regex being
  triggered, but the simulator's rubric may still reward this letter shape more than real clients do.
- Rules-mode template letters only. With an LLM writer the strategy would be a prompt instruction,
  and the effect may differ.
- One seed per world. Noise per proposal is seeded by the letter text, so each arm sees independent
  noise on the same clients.

Provenance: the run started from commit `cc55941` (writer strategies). `ab.json` records `e4461fd`
because the sha is read when the summary is written; no commit in between changed writer behaviour.
