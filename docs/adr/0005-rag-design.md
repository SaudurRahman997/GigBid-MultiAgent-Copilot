# ADR 0005: RAG design (models, index, variants, verification)

- Status: accepted (deployed variant chosen by `evals/runners/rag_eval.py`, not here)
- Date: 2026-11-15

## Context
Phase 4 needs V0 + at least four variants (V1, V2, V3, V8 required), claim verification and an
evaluation that picks the deployed variant. It must run on a laptop CPU (no usable GPU: 4 GB
Quadro) and on a small VM, and evaluations must be reproducible.

## Decisions
1. **fastembed (ONNX) instead of PyTorch.** Same models, no torch install, CPU-friendly, also
   usable on the VM.
   - Embeddings: **nomic-embed-text-v1.5** (768-d) - one of the two spec options. BGE-M3 is not
     available in fastembed; nomic is the spec's alternative. Uses the model's
     `search_query:` / `search_document:` prefixes.
   - Reranker: **bge-reranker-v2-m3, int8 build** (0.57 GB vs 2.27 GB).
   Measured on this laptop: ~5 chunks/s to embed, ~2.3 pairs/s to rerank.
2. **Content-addressed caches** (`var/cache/rag`) for embeddings and rerank scores: re-running an
   eval is fast and returns identical numbers.
3. **Rerank budget.** At ~2.3 pairs/s, V3 reranks the top 15 fused chunks (distinct documents)
   against one combined query (~15 pairs/job, ~6.5 s). Scoring every requirement separately
   would be 5-8x slower; recorded as a possible later optimisation if a GPU/API reranker is used.
4. **Two chunkings.** Fixed 200-word windows (V0, the naive baseline) and structure-aware chunks
   (Markdown sections, one CV engagement per chunk, whole code files/reviews/proposals, title
   prefix) for V1+.
5. **pgvector is the one vector store** in deployment (HNSW, cosine), with incremental sync by
   chunk content hash. Offline evals use an in-memory index with the same cosine metric for
   speed; an integration test checks the two rank alike.
6. **Document-level evaluation.** Gold is evidence-level, so chunk rankings are collapsed to one
   hit per evidence id (best chunk). Metrics: Recall@5, MRR, nDCG@10 (graded: anchor evidence 2,
   same-archetype case studies 1) and, added after the checkpoint, project recall@5.
7. **V8 grader = cross-encoder threshold, rewrite = taxonomy expansion** (deterministic). An LLM
   grader/rewriter is possible later but would make evals non-reproducible and cost tokens.
8. **Claim verification** defaults to the deterministic RerankJudge with a strict number check;
   the LLM judge is available. Judge quality: constructed claim set (labels by construction) for
   thresholds, Cohen's kappa vs 30 human-labelled proposals for calibration.

## Consequences
- Results depend on the embedding model; switching models invalidates the cache, not the code.
- Template-written synthetic text is less varied than real portfolios (limitation in the report).

## Decision on what ships (added after measuring the app's own search path)

`search_evidence` serves **bm25_baseline** (lexical search over title and text). In the
one-search-per-job study V2 hybrid ranked first of V0 to V8, but the app does not search that way:
the Fit Matcher searches once per requirement and the Writer merges the results.
`evals/runners/app_path_eval.py` replays that path (465 dev jobs with gold evidence). The rule,
fixed before the full run, was: highest writer recall, ties broken by latency. BM25 had writer
recall 0.295 against 0.257 for V2, 0.231 for V0 and 0.225 for V1, and its letters cited a gold
item more often (0.660 against 0.600 for V2)
(`evals/results/rag/dev/app_path.json`). It also needs no embedding model. Limits: the result is
not uniform (on ai_ml, V0 had higher writer recall than BM25: 0.246 against 0.212), the data is
synthetic, and V3, V4 and V8 were left out because of their reranking latency. Claim
verification is a separate path and keeps `verify.retrieval_variant: v2_hybrid`.
