"""RAG unit tests: loaders, chunking, query decomposition, fusion, variants, metrics, verify.
Use HashEmbedder / OverlapReranker so no model is downloaded."""

from __future__ import annotations

import pytest

from evals.metrics import cohen_kappa, mrr, ndcg_at_k, recall_at_k
from rag.chunking import fixed_chunks, structured_chunks
from rag.ingest.loaders import Document, detect_skills, load_persona, pdf_text
from rag.models import HashEmbedder, OverlapReranker
from rag.query import RetrievalQuery, from_job
from rag.variants import CONTEXT_VARIANTS
from rag.variants.base import build_context, rag_config, rrf
from rag.variants.pipeline import Pipeline
from rag.variants.v4_outcome import outcome_multiplier
from rag.verify import RerankJudge, numbers, repair, split_claims, unsupported_rate, verify

CFG = rag_config()


def doc(i, type_="case_study", text="", outcome=None, title=None, skills=()):
    return Document(
        id=f"t:{type_}:{i}",
        persona="t",
        type=type_,
        title=title or f"doc {i}",
        text=text,
        source="x",
        outcome=outcome,
        skills=tuple(skills),
    )


DOCS = (
    doc(
        1,
        text="I built a retrieval pipeline over pgvector that answers questions from PDFs with citations.",
    ),
    doc(
        2, text="I trained a gradient boosted churn model with scikit-learn that cut churn by 20%."
    ),
    doc(
        3,
        "review",
        "Great work on our Power BI sales dashboard, the managers love it.",
        outcome="5.0/5",
    ),
    doc(4, "proposal", "Your shop needs a churn model and a weekly report.", outcome="won"),
    doc(5, "proposal", "Your shop needs a churn model and a weekly report too.", outcome="ignored"),
)


@pytest.fixture(scope="module")
def ctx():
    return build_context("t", HashEmbedder(), OverlapReranker(), CFG, docs=DOCS)


# ----------------------------------------------------------------------------- loaders + chunking


def test_loaders_read_raw_files_with_metadata():
    docs = load_persona("ai_ml")
    types = {d.type for d in docs}
    assert types == {"cv", "case_study", "review", "readme", "code", "proposal"}
    case = next(d for d in docs if d.type == "case_study")
    assert set(case.metadata) >= {
        "persona",
        "type",
        "project",
        "skills",
        "date",
        "client_industry",
        "outcome",
    }
    assert case.project_id and case.skills and case.outcome
    assert next(d for d in docs if d.type == "cv").text.startswith("Aiko")  # parsed from the PDF


def test_pdf_text_extracts_cv():
    from pathlib import Path

    assert "Skills" in pdf_text(Path("data/personas/fullstack/cv.pdf"))


def test_detect_skills_uses_taxonomy_and_aliases():
    found = detect_skills("We use ReactJS with a Node.js API and Power BI dashboards")
    assert {"react", "node.js", "microsoft power bi"} <= set(found)


def test_fixed_chunks_overlap_and_cover_text():
    d = doc(9, text=" ".join(f"w{i}" for i in range(450)))
    chunks = fixed_chunks(d, size=200, overlap=40)
    assert len(chunks) == 3 and chunks[1].text.split()[0] == "w160"
    assert chunks[-1].text.split()[-1] == "w449"


def test_structured_chunks_keep_title_and_respect_max_words():
    text = "# Title\n\n" + "\n\n".join(" ".join(["word"] * 120) for _ in range(3))
    chunks = structured_chunks(doc(8, text=text, title="My case"), max_words=150)
    assert len(chunks) == 3 and all(c.text.startswith("My case\n") for c in chunks)
    assert all(c.doc_id == "t:case_study:8" for c in chunks)


# ----------------------------------------------------------------------------- queries + fusion


def test_from_job_decomposes_and_resolves_vague_bullets():
    q = from_job(
        "Help wanted: churn model",
        "We're a store and we want to predict churn.\n\nWhat we need:\n"
        "- Strong scikit-learn skills (must have)\n- You have shipped something like this before (tell us about it)",
    )
    assert q.requirements[0].startswith("We're a store")
    assert any(r.startswith("scikit-learn (Help wanted") for r in q.requirements)
    assert any(r.startswith("experience delivering:") for r in q.requirements)
    assert RetrievalQuery.single("python").sub_queries() == ["python"]


def test_rrf_rewards_items_ranked_high_in_many_lists(ctx):
    a, b, c = ctx.structured[0], ctx.structured[1], ctx.structured[2]
    fused = rrf([[(a, 1), (b, 1)], [(b, 1), (c, 1)], [(b, 1), (a, 1)]], k=60)
    assert fused[0][0].chunk_id == b.chunk_id


# ----------------------------------------------------------------------------- variants


@pytest.mark.parametrize("name", sorted(CONTEXT_VARIANTS))
def test_every_variant_returns_document_hits(ctx, name):
    v = CONTEXT_VARIANTS[name](ctx)
    hits = v.retrieve(
        RetrievalQuery("churn model scikit-learn", ("churn model", "scikit-learn")), k=3
    )
    ids = [h.doc.id for h in hits]
    assert len(ids) == len(set(ids)) <= 3  # one hit per document
    if name != "v8_corrective":
        assert ids, name
    assert v.search("churn model", k=2) is not None


def test_hybrid_finds_exact_tool_name(ctx):
    hits = CONTEXT_VARIANTS["v2_hybrid"](ctx).search("Power BI", k=2)
    assert hits[0].doc.id == "t:review:3"


def test_filters_apply_at_document_level(ctx):
    from rag.retriever import EvidenceFilters

    hits = CONTEXT_VARIANTS["v2_hybrid"](ctx).search(
        "churn model", k=5, filters=EvidenceFilters(types=["proposal"])
    )
    assert hits and all(h.doc.type == "proposal" for h in hits)


def test_outcome_multiplier():
    boost = CFG["outcome_boost"]
    assert outcome_multiplier(doc(1, "proposal", outcome="won"), boost) > 1
    assert outcome_multiplier(doc(1, "proposal", outcome="ignored"), boost) < 1
    assert outcome_multiplier(doc(1, "review", outcome="4.9/5"), boost) == boost["high_rating"]
    assert (
        outcome_multiplier(doc(1, outcome="delivered; rated 5.0/5; rehired"), boost)
        > boost["rehired"]
    )


def test_outcome_aware_prefers_won_proposal(ctx):
    hits = CONTEXT_VARIANTS["v4_outcome"](ctx).retrieve(
        RetrievalQuery.single("shop needs a churn model weekly report"), 5
    )
    ids = [h.doc.id for h in hits]
    assert ids.index("t:proposal:4") < ids.index("t:proposal:5")


def test_corrective_refuses_when_no_evidence_is_good():
    cfg = {
        **CFG,
        "crag": {"max_rounds": 2, "min_rerank_score": 50.0, "min_good_hits": 1},
    }  # impossible bar
    c = build_context("t", HashEmbedder(), OverlapReranker(), cfg, docs=DOCS)
    v = CONTEXT_VARIANTS["v8_corrective"](c)
    state = v.run(RetrievalQuery.single("Unity 3D game development"))
    assert state["refused"] and state["round"] == 2 and v.search("Unity") == []


def test_pipeline_flags_name_the_ablation(ctx):
    assert Pipeline(ctx).variant == "all_on"
    assert Pipeline(ctx, bm25=False).variant == "no_bm25"
    with pytest.raises(ValueError):
        Pipeline(ctx, nonsense=False)
    assert Pipeline(ctx, rerank=False, outcome=False).search("churn", 2)


# ----------------------------------------------------------------------------- metrics


def test_retrieval_metrics():
    ranked = ["a", "x", "b", "y", "z", "c"]
    assert recall_at_k(ranked, {"a", "b", "c"}, 5) == pytest.approx(2 / 3)
    assert mrr(ranked, {"b"}) == pytest.approx(1 / 3)
    assert ndcg_at_k(["a", "b"], {"a": 2, "b": 1}) == pytest.approx(1.0)
    assert ndcg_at_k(["b", "a"], {"a": 2, "b": 1}) < 1.0
    assert recall_at_k(ranked, set(), 5) == 0.0


def test_cohen_kappa():
    assert cohen_kappa(list("aabb"), list("aabb")) == 1.0
    assert cohen_kappa(list("aabb"), list("abab")) == pytest.approx(0.0)
    with pytest.raises(ValueError):
        cohen_kappa(["a"], ["a", "b"])


# ----------------------------------------------------------------------------- claim verification


DRAFT = """You need a chatbot over your PDFs.

I built a retrieval pipeline over pgvector that answers questions from PDFs with citations [t:case_study:1]. I trained a churn model with scikit-learn that cut churn by 90%. I have ten years of Kubernetes experience at Google. Happy to share a plan."""


def test_split_claims_skips_pleasantries_and_keeps_citations():
    claims = split_claims(DRAFT)
    assert [c for c, _ in claims][0].startswith("I built a retrieval pipeline")
    assert claims[0][1] == ["t:case_study:1"]
    assert len(claims) == 3
    assert numbers("cut churn by 90% in 2 weeks") == {"90%", "2"}


def test_verify_and_repair(ctx):
    judge = RerankJudge(OverlapReranker(), support_logit=0.5, partial_logit=0.25)
    checks = verify(DRAFT, CONTEXT_VARIANTS["v2_hybrid"](ctx), judge, k=3)
    status = {c.text[:20]: c.status for c in checks}
    assert status["I built a retrieval "] == "supported"
    assert status["I trained a churn mo"] == "partial"  # 90% is not in the evidence
    assert status["I have ten years of "] == "unsupported"
    cleaned, report = repair(DRAFT, checks)
    assert "Kubernetes" not in cleaned and "retrieval pipeline" in cleaned
    assert (
        report["unsupported_rate_before"] == pytest.approx(1 / 3, abs=1e-3)
        and report["unsupported_rate_after"] == 0.0
    )
    assert unsupported_rate([]) == 0.0
