"""
Agent core (Days 1-5): prompt -> model -> tool calls -> structured answer.

Flow per question:
  1. Model classifies product (esign / dpdp / both / ambiguous) and
     calls search_answer_library / get_answer_entry as needed.
  2. Model returns a structured JSON answer conforming to ANSWER_SCHEMA.
  3. Code-level guardrails run on the answer (guardrails.py).
  4. Everything is written to the audit trail (audit.py).

Max-step limit prevents runaway loops (Day 1 guardrail).
"""

import json
import os
import time

import anthropic

from audit import log_interaction
from guardrails import apply_guardrails
from library import get_answer_entry, search_answer_library

MODEL = os.environ.get("AGENT_MODEL", "claude-sonnet-4-6")
MAX_STEPS = 6

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client

TOOLS = [
    {
        "name": "search_answer_library",
        "description": (
            "Search Certinal's approved answer library for entries relevant to a prospect's "
            "question. Returns entry IDs, product, topic, approval status, and answer previews. "
            "Always search before answering."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The prospect's question or key terms."},
                "product": {
                    "type": "string",
                    "enum": ["esign", "dpdp", "both", "any"],
                    "description": "Which product the question concerns. Use 'any' if unsure.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_answer_entry",
        "description": "Fetch the full text and metadata of a library entry by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {"entry_id": {"type": "string"}},
            "required": ["entry_id"],
        },
    },
]

SYSTEM_PROMPT = """You are Certinal's RFP and prospect-question answering agent, used internally \
by Certinal's sales team (AEs, RSMs, presales, sales leadership).

Certinal has two products:
1. Certinal eSign: enterprise eSignature and digital transaction management. Competes with \
DocuSign and Adobe Acrobat Sign.
2. Certinal DPDP suite: consent management for India's DPDP Act 2023 / DPDP Rules 2025 \
(ConsentFlow, ConsentRights, Rights Portal, ConsentMap, ConsentGovern).

Your job: given a prospect/customer question, produce a defensible draft answer the salesperson \
can review and send.

Rules that are never broken:
- ALWAYS search the answer library before answering. Ground answers in library entries.
- NEVER invent a capability, certification, integration, or compliance status. If the library \
does not cover it, say so and set verify_required to true.
- NEVER claim HITRUST certification.
- 21 CFR Part 11 and HIPAA are always framed as "designed to support", never "compliant" or \
"certified".
- No specific cost-reduction figures unless they come verbatim from an approved library entry.
- First classify which product the question concerns: esign, dpdp, both, or ambiguous. If \
ambiguous, ask nothing; answer what you can and flag the ambiguity.
- Competitive questions get factual differentiator framing, never disparagement of DocuSign, \
Adobe, or any vendor.

After using tools, respond with ONLY a JSON object (no markdown fences, no preamble):
{
  "product": "esign" | "dpdp" | "both" | "ambiguous",
  "answer": "the draft answer text, written in professional RFP-ready language",
  "source_ids": ["IDs of library entries the answer is based on, empty if none"],
  "confidence": "high" | "medium" | "low",
  "verify_required": true | false,
  "verify_reason": "why verification is needed, empty string if not",
  "notes_for_salesperson": "anything the rep should know before sending, empty string if none"
}"""


def _execute_tool(name: str, tool_input: dict):
    if name == "search_answer_library":
        return search_answer_library(
            query=tool_input["query"],
            product=tool_input.get("product", "any"),
        )
    if name == "get_answer_entry":
        return get_answer_entry(tool_input["entry_id"]) or {"error": f"No entry {tool_input['entry_id']}"}
    return {"error": f"Unknown tool {name}"}


def _parse_structured(text: str) -> dict:
    clean = text.strip()
    if clean.startswith("```"):
        clean = clean.strip("`")
        if clean.startswith("json"):
            clean = clean[4:]
    try:
        return json.loads(clean.strip())
    except json.JSONDecodeError:
        # Schema-validation failure path (Week 2 will make this a retry;
        # for now it degrades explicitly rather than silently).
        return {
            "product": "ambiguous",
            "answer": text,
            "source_ids": [],
            "confidence": "low",
            "verify_required": True,
            "verify_reason": "Agent output failed schema parsing. Treat as unverified draft.",
            "notes_for_salesperson": "Structured output parsing failed; raw model text shown.",
        }


def answer_question(question: str, user: str = "unknown") -> dict:
    """Run the full agent loop for one question. Returns the structured, guardrailed answer."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return {
            "product": "ambiguous",
            "answer": (
                "The server is deployed and running, but the Anthropic API key has not been "
                "added yet, so I can't generate answers. Add ANTHROPIC_API_KEY in the host's "
                "environment variables and this message will disappear."
            ),
            "source_ids": [],
            "confidence": "low",
            "verify_required": True,
            "verify_reason": "API key not configured.",
            "compliance_flags": [],
            "blocked": False,
            "notes_for_salesperson": "Setup in progress. Contact Ashutosh.",
        }

    start = time.time()
    messages = [{"role": "user", "content": question}]
    tool_calls_log = []
    input_tokens = output_tokens = 0

    response = None
    for _ in range(MAX_STEPS):
        response = _get_client().messages.create(
            model=MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens

        if response.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = _execute_tool(block.name, block.input)
                tool_calls_log.append({"tool": block.name, "input": block.input, "result": result})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False),
                })
        messages.append({"role": "user", "content": tool_results})

    final_text = "".join(b.text for b in response.content if b.type == "text")
    structured = _parse_structured(final_text)

    # Code-level guardrails on top of whatever the model produced.
    source_ids = structured.get("source_ids", [])
    statuses = []
    for sid in source_ids:
        entry = get_answer_entry(sid)
        statuses.append(entry["status"] if entry else "unknown")

    guard = apply_guardrails(structured.get("answer", ""), source_ids, statuses)
    structured["answer"] = guard.answer
    structured["compliance_flags"] = guard.compliance_flags
    structured["blocked"] = guard.blocked
    if guard.verify_required:
        structured["verify_required"] = True
        if guard.verify_reason:
            structured["verify_reason"] = guard.verify_reason

    latency_ms = int((time.time() - start) * 1000)
    log_interaction({
        "user": user,
        "question": question,
        "product": structured.get("product"),
        "answer": structured.get("answer"),
        "source_ids": source_ids,
        "confidence": structured.get("confidence"),
        "verify_required": structured.get("verify_required"),
        "verify_reason": structured.get("verify_reason", ""),
        "compliance_flags": structured.get("compliance_flags", []),
        "blocked": structured.get("blocked", False),
        "tool_calls": tool_calls_log,
        "model": MODEL,
        "latency_ms": latency_ms,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    })

    return structured
