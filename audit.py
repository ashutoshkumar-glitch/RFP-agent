"""
Audit trail (Day 6): append-only JSONL log of every interaction.

One record per answered question:
  timestamp, user, product, question, answer, source_ids, confidence,
  verify_required, verify_reason, compliance_flags, blocked,
  tool_calls, model, latency_ms, input_tokens, output_tokens

This log is simultaneously:
  - the compliance record (what did the agent tell whom, based on what source)
  - the manager's daily-summary input (daily_summary.py)
  - the future golden dataset seed (Week 3: real questions from real usage)
  - the cost ledger (Week 3: cost per query from token counts)
"""

import json
import time
from pathlib import Path

AUDIT_PATH = Path(__file__).parent / "data" / "audit_log.jsonl"


def log_interaction(record: dict) -> None:
    record["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_PATH, "a") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_log(since: str | None = None) -> list:
    """Read audit records, optionally filtered to timestamps >= `since` (ISO date)."""
    if not AUDIT_PATH.exists():
        return []
    records = []
    with open(AUDIT_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if since is None or rec.get("timestamp", "") >= since:
                records.append(rec)
    return records
