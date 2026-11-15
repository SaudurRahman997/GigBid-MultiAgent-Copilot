"""Registry of retrieval variants (name -> class taking the persona corpus)."""

from rag.variants.bm25 import BM25Retriever

VARIANTS = {
    BM25Retriever.variant: BM25Retriever,
}
