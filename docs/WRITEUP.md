# Smarter retrieval made my freelancing agent worse

_Technical write-up — GigBid (AI-4016 R&D Assignment II). Every number below comes from a file in
`evals/results/` written by a runner in `evals/runners/`; the file is named next to the number._

## The setup

GigBid is a multi-agent copilot for freelancers. Given a job post, three agents run in parallel — a
Job Analyst that turns the post into requirements, a Risk Assessor that looks for scams, prompt
injections and bad clients, and a Fit Matcher that looks for evidence in the freelancer's portfolio —
and a decision node chooses bid, skip or watch. If it bids, a Writer drafts a proposal, a verifier
checks every claim against the portfolio, a Critic sends weak drafts back (at most twice), a
Compliance node blocks contact details and policy violations, and finally a human approves, edits
or rejects. Nothing is sent without that approval.

The whole proposal stands on retrieval. A proposal that says "I built a RAG pipeline for a legal
team that cut search time by 40%" is only honest if that project exists in the portfolio, and only
persuasive if it is the *right* project for this job. So before writing any agent code I built six
retrieval variants behind one interface and wrote down what I expected each to do
(`evals/HYPOTHESES.md`).

My expectations were the textbook ones. Splitting a job into one query per requirement (V1) should
find evidence for every requirement instead of only the dominant one. Adding a cross-encoder
reranker (V3) should push the most relevant items to the top. Boosting evidence from projects that
won (V4) should help reply rates. A corrective RAG loop (V8) that grades its own results and retries
should beat everything on recall.

## What actually happened

On the 600-job dev set across three personas (`evals/results/rag/dev/*.json`), the ranking was
almost the reverse of my hypotheses:

- V2, plain hybrid BM25 + dense retrieval with reciprocal-rank fusion, was best: Recall@5 0.216,
  MRR 0.402, nDCG@10 0.297, with a p95 latency of 19 ms.
- V0, naive dense retrieval, was a close second (Recall@5 0.204, MRR 0.394).
- V1 decomposition was *below* naive (Recall@5 0.189, MRR 0.331).
- V3 with the reranker was below hybrid (Recall@5 0.193, MRR 0.337) and cost about 11 seconds p95
  on CPU.
- V8 corrective RAG had the lowest recall (0.174) and a p95 of almost 26 seconds.

The ablation made the point sharper (`evals/results/rag/dev/ablation.json`). Starting from the V2
pipeline, which still issues one query per requirement, and removing components one at a time,
the single best configuration I measured was the one **without** per-requirement decomposition:
Recall@5 0.282 and MRR 0.488 — +0.066 and +0.086 over V2. Removing the BM25 channel hurt (MRR
−0.071). Changing the chunking strategy barely mattered.

So the two "smart" components — decomposition and reranking — were the ones making retrieval worse.

## Why

Looking at individual jobs (`*.jobs.jsonl` next to each result file) explained both failures.

**Decomposition destroys the context that makes evidence relevant.** A job post says something like
"build a retrieval assistant over our support tickets; must have Python and a vector database;
nice to have experience with healthcare data." Split into queries, that becomes "Python",
"vector database" and "healthcare data". Each fragment matches dozens of portfolio items equally
well — every project uses Python — and the one project that is actually about a support-ticket
assistant is no longer the obvious winner, because no single query describes it. Retrieval quality
depends on the *combination* of requirements, and decomposition throws the combination away. The
breakdown fits this: the loss from decomposition is largest on jobs that list every skill
explicitly (Recall@5 0.184 vs 0.224 for naive), where each fragment is a bare skill name.

**The reranker had a length bias that matched the wrong document type.** Almost half of the gold
evidence in my dev set is short client reviews ("Delivered the churn model early and explained it
clearly to our team"). The cross-encoder consistently preferred long past proposals, which mention
many skills and look relevant to almost anything. On the slice of jobs that name every skill
explicitly, reranking did help (Recall@5 0.230 vs 0.207 for V2); everywhere else it pushed reviews
out of the top five. I only saw this because I added a second metric, project recall@5 — whether
the right *project* appears at all, from any document type — after noticing that proposals took
about half of the top-5 slots.

**Corrective RAG is a safety feature, not a recall feature.** V8's value was its refusals: on jobs
where the freelancer genuinely has no relevant evidence, it refused 87.4% of the time, which is
exactly what you want before a writer invents a project. The price was refusing on 9.7% of jobs
where evidence did exist, plus the latency.

## Did better retrieval sell more?

I could not answer that question with retrieval metrics alone, so I ran the same 30 bid-worthy jobs
per persona through GigSim, my marketplace simulator, with a deterministic template writer, so only
the evidence changed (`evals/results/gigsim/outcomes.json`). Grounding mattered enormously: a generic
proposal got a 0.111 reply rate, while every grounded variant got between 0.333 and 0.422. Between
retrieval variants, though, the differences were small and did not follow retrieval quality
exactly — V3 covered more must-have requirements (0.64) than V2 (0.61) but did not get more
replies. The simulated client reacts to whether the top evidence is relevant and whether the price
is sane; coverage beyond a point does not move it. The lesson I took: retrieval metrics are
necessary for debugging but are not the objective. The objective is the outcome, and for that the
cheapest variant was as good as any.

## What the agents added on top

Retrieval was not the only place where simpler beat clever, but the multi-agent structure did pay
for itself in decisions. On all 600 dev jobs, the graph's bid/skip macro-F1 was 0.870 against 0.696
for a keyword baseline (`evals/results/decision/*.json`). The improvement comes almost entirely from
the parallel Risk Assessor and Fit Matcher: client history (low ratings, low hire rates, unverified
clients with many posts) and must-have skill coverage are signals a keyword rule cannot see. Both
approaches caught every scam (recall 1.000). And the claim verifier cut unsupported claims in drafts
from 0.325 to 0.014 after repair (`evals/results/verify/verify_eval.json`) — the single biggest
honesty improvement in the system, and it does not depend on which retriever is used.

## What I would do differently

1. **Write the ablation before the variants.** I built five named variants and only found the best
   configuration by taking one of them apart. Treating components as switches from the start
   would have found it in one run.
2. **Measure by document type early.** Recall averaged over everything hid the fact that one
   document type was crowding out another. One extra metric explained most of the results.
3. **Keep the expensive components for the cases they help.** A reranker that helps only when a job
   names every skill can be turned on only for those jobs; corrective retrieval can run only when
   the first pass scores low. Both are cheap routing decisions in a LangGraph.

The most surprising finding, in one line: on a real portfolio, the retrieval tricks I was most
confident about made the agent worse, and I only found out because every number had to come from a
runner instead of from my expectations.
