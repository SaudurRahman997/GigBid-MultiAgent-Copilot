from evals.runners.app_path_eval import score_job, writer_evidence
from rag.corpus import load_corpus
from rag.retriever import get_retriever


def test_score_job_ignores_past_proposals_in_the_letter():
    ids = ["p:proposal:1", "p:case:01", "p:review:2", "p:case:09", "p:case:03"]
    s = score_job(ids, gold={"p:case:03", "p:review:2"}, related={"p:case:01"}, letter_n=3)
    assert s["writer_recall"] == 1.0
    assert s["writer_mrr"] == 1 / 3
    assert s["letter_hit"] == 1.0  # the letter cites case:01, review:2, case:09
    assert s["letter_precision"] == 2 / 3


def test_score_job_with_nothing_retrieved():
    assert score_job([], {"p:case:01"}, set(), 3) == {
        "writer_recall": 0.0,
        "writer_mrr": 0.0,
        "letter_hit": 0.0,
        "letter_precision": 0.0,
    }


def test_writer_evidence_is_unique_capped_and_from_the_portfolio():
    job = {
        "title": "Churn prediction model",
        "description": "
".join(
            ["Predict which customers will cancel.", "- Python (must have)", "- SQL"]
        ),
        "skills": ["scikit-learn"],
    }
    ids = writer_evidence(get_retriever("ai_ml", "bm25_baseline"), job)
    assert 0 < len(ids) <= 8
    assert len(ids) == len(set(ids))
    assert set(ids) <= {d.id for d in load_corpus("ai_ml")}
