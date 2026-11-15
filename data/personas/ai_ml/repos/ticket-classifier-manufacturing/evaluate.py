# SYNTHETIC sample code for GigBid persona ai_ml. provenance: personas@1f579ad2e496
import json
from statistics import mean


def recall_at_k(gold: set[str], ranked: list[str], k: int = 5) -> float:
    return len(gold & set(ranked[:k])) / max(len(gold), 1)


rows = [json.loads(line) for line in open("runs.jsonl")]
print("Recall@5", round(mean(recall_at_k(set(r["gold"]), r["ranked"]) for r in rows), 3))
