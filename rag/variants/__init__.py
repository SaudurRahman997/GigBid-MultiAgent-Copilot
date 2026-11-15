"""Registry of retrieval variants (name -> class taking a per-persona context or corpus).

bm25_baseline is the interim Phase 3 retriever (takes the plain corpus); V0-V8 take a Context
built by rag.variants.base.build_context.
"""

from rag.variants.bm25 import BM25Retriever
from rag.variants.v0_naive import V0Naive
from rag.variants.v1_decompose import V1Decompose
from rag.variants.v2_hybrid import V2Hybrid
from rag.variants.v3_rerank import V3Rerank
from rag.variants.v4_outcome import V4Outcome
from rag.variants.v8_corrective import V8Corrective

CONTEXT_VARIANTS = {v.variant: v for v in (V0Naive, V1Decompose, V2Hybrid, V3Rerank, V4Outcome, V8Corrective)}
VARIANTS = {BM25Retriever.variant: BM25Retriever, **CONTEXT_VARIANTS}
