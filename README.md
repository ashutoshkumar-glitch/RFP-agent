# Certinal Answer Desk (RFP Agent)

Internal agent for the Certinal sales team. Takes a prospect or RFP question
(eSign or DPDP), retrieves from the approved answer library, and returns a
draft answer with sources, confidence, and a mandatory VERIFY flag on anything
not covered by an approved entry. Every interaction is logged; a daily digest
for the Head of Sales is generated from the log.

## Run locally

```bash
pip install fastapi uvicorn anthropic
export ANTHROPIC_API_KEY=sk-ant-...        # server-side only, never in the frontend
uvicorn app:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 and ask a question.

Daily digest (manual run):

```bash
python daily_summary.py
```

Schedule it (weekdays 6pm):

```
0 18 * * 1-5  cd /path/to/certinal-rfp-agent && python daily_summary.py
```

## Files

| File | Purpose | Curriculum day |
|---|---|---|
| agent.py | Agent loop, tool use, product routing, structured output | 1-5 |
| library.py | Answer library search + fetch (the two tools) | 3 |
| guardrails.py | Compliance rules enforced in code | 4 |
| audit.py | Append-only JSONL audit trail | 6 |
| daily_summary.py | Manager digest from the audit trail | 6 |
| app.py + static/index.html | Web app for the team | 7 |
| data/answer_library.json | Approved answer corpus (currently PLACEHOLDERS) | prerequisite |

## Status and roadmap

Done (Week 1 skeleton): agent loop, two tools, coded guardrails (HITRUST block,
HIPAA / 21 CFR Part 11 framing, cost-figure flag, no-source-means-verify),
context handling for single questions, audit trail, web UI, daily digest.

Before team rollout:
1. Replace placeholder library entries with real approved answers (blocking).
2. Add simple auth to the app and protect /api/digest.
3. Deploy behind the company network or on a small VM / PaaS.

Week 2: document upload (Word/PDF question extraction), JSON schema validation
with retry on invalid output, checkpointing for long questionnaires, resume
after failure, explicit failure handling per failure mode.

Week 3: retry logic with backoff on API calls, failure taxonomy from real audit
data, 20-question golden dataset from actual usage, eval suite, cost per query
from the token counts already being logged.

Week 4: workflow audit, architecture writeup, evaluation report, deployment
controls, business case (hours saved per RFP x RFPs per quarter).

## Security notes

- The API key lives only in the server environment.
- The audit log contains prospect questions; treat data/ as confidential.
- The frontend never sees library internals beyond the sources cited.
