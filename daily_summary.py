"""
Daily manager digest: reads the audit trail and produces an email-ready summary.

Run manually:   python daily_summary.py
Run on schedule: cron entry, e.g.  0 18 * * 1-5  cd /path && python daily_summary.py

Output covers:
  - who used the agent and how much, by product
  - what got flagged verify_required (the rep should not send these unreviewed)
  - guardrail trips and blocks (compliance exposure)
  - questions the library could not answer (= your library backlog)
  - total token cost for the day

The digest is written to data/summaries/YYYY-MM-DD.md.
Wiring it to email (Gmail API / SMTP) is a Week 2+ addition.
"""

import json
import os
import time
from collections import Counter
from pathlib import Path

import anthropic

from audit import read_log

MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-4-6")
SUMMARY_DIR = Path(__file__).parent / "data" / "summaries"


def build_digest(date: str | None = None) -> str:
    date = date or time.strftime("%Y-%m-%d")
    records = [r for r in read_log(since=date) if r["timestamp"].startswith(date)]

    if not records:
        return f"# Agent digest {date}\n\nNo usage today."

    users = Counter(r.get("user", "unknown") for r in records)
    products = Counter(r.get("product", "unknown") for r in records)
    verify_items = [r for r in records if r.get("verify_required")]
    blocked_items = [r for r in records if r.get("blocked")]
    no_source = [r for r in records if not r.get("source_ids")]
    tokens_in = sum(r.get("input_tokens", 0) for r in records)
    tokens_out = sum(r.get("output_tokens", 0) for r in records)

    stats = {
        "date": date,
        "total_questions": len(records),
        "by_user": dict(users),
        "by_product": dict(products),
        "verify_required_count": len(verify_items),
        "blocked_count": len(blocked_items),
        "unanswerable_no_source": len(no_source),
        "tokens": {"input": tokens_in, "output": tokens_out},
    }

    detail = [
        {
            "user": r.get("user"),
            "question": r.get("question", "")[:300],
            "product": r.get("product"),
            "verify_required": r.get("verify_required"),
            "verify_reason": r.get("verify_reason", "")[:200],
            "compliance_flags": r.get("compliance_flags", []),
        }
        for r in records
    ]

    client = anthropic.Anthropic()
    prompt = f"""You are writing the daily digest for the Head of Sales about his team's use of \
the internal RFP-answering agent. Be concise, candid, and action-oriented. Lead with the answer.

Stats: {json.dumps(stats)}

Interaction detail: {json.dumps(detail, ensure_ascii=False)}

Write a short markdown digest with these sections:
1. Usage at a glance (one line: volume, users, product split).
2. Needs your attention: every verify_required or blocked item, who asked it, and why it was \
flagged. These are answers reps must not send unreviewed.
3. Library gaps: questions with no library source, grouped by theme. These are candidates to \
add to the approved library.
4. One-line cost note (tokens used).

No preamble. No emdash characters anywhere."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    digest = "".join(b.text for b in resp.content if b.type == "text")

    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    out_path = SUMMARY_DIR / f"{date}.md"
    out_path.write_text(digest)
    return digest


if __name__ == "__main__":
    print(build_digest())
