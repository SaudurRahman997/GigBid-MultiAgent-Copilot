# SYNTHETIC sample code for GigBid persona ai_ml. provenance: personas@228603469f77
from fastapi import FastAPI
from pydantic import BaseModel

from retrieval import search, rerank
from llm import answer_with_citations

app = FastAPI(title="doc-qa-service")


class Question(BaseModel):
    text: str
    k: int = 5


@app.post("/ask")
def ask(q: Question) -> dict:
    hits = rerank(q.text, search(q.text, k=q.k * 4))[: q.k]
    return answer_with_citations(q.text, hits)  # every sentence cites a chunk id
