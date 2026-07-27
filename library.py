"""
Answer library: load, search, and fetch approved Q&A entries.
Day 3 of the curriculum: these two functions are the agent's tools.

Search is deliberately simple (keyword scoring) for v1. Upgrading to
embeddings is a later iteration and should be justified by eval results
(Week 3), not by instinct.
"""

import json
import re
from pathlib import Path

LIBRARY_PATH = Path(__file__).parent / "data" / "answer_library.json"

_STOPWORDS = {
    "the", "a", "an", "is", "are", "do", "does", "your", "you", "we", "our",
    "how", "what", "which", "of", "for", "to", "and", "or", "in", "on",
    "with", "support", "platform", "solution", "can", "have", "has",
}


def load_library() -> list:
    with open(LIBRARY_PATH) as f:
        return json.load(f)["entries"]


def _tokens(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS}


def search_answer_library(query: str, product: str = "any", top_k: int = 3) -> list:
    """Tool 1: keyword search over question patterns, topics, and answers."""
    entries = load_library()
    q_tokens = _tokens(query)
    scored = []
    for e in entries:
        if product not in ("any", "both") and e["product"] not in (product, "both"):
            continue
        hay = " ".join(e["question_patterns"]) + " " + e["topic"] + " " + e["answer"]
        overlap = len(q_tokens & _tokens(hay))
        if overlap > 0:
            scored.append((overlap, e))
    scored.sort(key=lambda x: -x[0])
    return [
        {
            "id": e["id"],
            "product": e["product"],
            "topic": e["topic"],
            "status": e["status"],
            "answer_preview": e["answer"][:200],
        }
        for _, e in scored[:top_k]
    ]


def get_answer_entry(entry_id: str) -> dict | None:
    """Tool 2: fetch a full entry by ID."""
    for e in load_library():
        if e["id"] == entry_id:
            return e
    return None
