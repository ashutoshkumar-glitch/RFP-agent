"""
Guardrails: compliance rules enforced in code, applied to every agent answer
AFTER generation and BEFORE the answer reaches the user.

These encode Certinal's standing outreach/RFP compliance rules:
  1. Never claim HITRUST certification.
  2. 21 CFR Part 11 and HIPAA must be framed as "designed to support",
     never as flat "compliant" / "certified" claims.
  3. No unverified cost-reduction figures.
  4. Any answer without an approved library source must carry a VERIFY flag.

If a rule trips, the answer is either rewritten-flagged or blocked.
The audit log records every trip so rule effectiveness is measurable (Week 3).
"""

import re
from dataclasses import dataclass, field


@dataclass
class GuardrailResult:
    answer: str
    compliance_flags: list = field(default_factory=list)
    verify_required: bool = False
    verify_reason: str = ""
    blocked: bool = False


# Rule 1: HITRUST claims are never allowed as affirmative statements.
HITRUST_CLAIM = re.compile(
    r"\b(hitrust)\b(?![^.]*\b(not|no|verify|unable|cannot|don't|do not)\b)",
    re.IGNORECASE,
)

# Rule 2: flat compliance claims for regulated frameworks.
# Matches "HIPAA compliant", "compliant with 21 CFR Part 11", "certified for HIPAA", etc.
FLAT_COMPLIANCE_CLAIM = re.compile(
    r"\b(?:is|are|fully|100%)\s+(?:hipaa|21\s*cfr(?:\s*part)?\s*11)[\s-]*(?:compliant|certified)"
    r"|\b(?:hipaa|21\s*cfr(?:\s*part)?\s*11)[\s-]*(?:compliant|certified)\b"
    r"|\bcompliant\s+with\s+(?:hipaa|21\s*cfr(?:\s*part)?\s*11)\b"
    r"|\bcertified\s+(?:for|under)\s+(?:hipaa|21\s*cfr(?:\s*part)?\s*11)\b",
    re.IGNORECASE,
)

APPROVED_FRAMING = "designed to support"

# Rule 3: specific cost/savings percentages or dollar figures.
COST_FIGURE = re.compile(
    r"(?:save|reduc\w+|cut|lower)\w*[^.]{0,60}?(?:\d{1,3}\s*%|\$\s?[\d,]+)",
    re.IGNORECASE,
)


def apply_guardrails(answer: str, source_ids: list, source_statuses: list) -> GuardrailResult:
    result = GuardrailResult(answer=answer)

    # Rule 1: HITRUST
    if HITRUST_CLAIM.search(answer):
        result.blocked = True
        result.compliance_flags.append("BLOCKED: affirmative HITRUST reference. Certinal does not claim HITRUST certification.")
        result.answer = (
            "This answer was withheld by a compliance guardrail (HITRUST reference). "
            "Certinal's approved position on HITRUST must come from the compliance owner. "
            "Please contact Ashutosh / InfoSec before responding to this question."
        )
        return result

    # Rule 2: flat HIPAA / 21 CFR Part 11 compliance claims
    if FLAT_COMPLIANCE_CLAIM.search(answer) and APPROVED_FRAMING not in answer.lower():
        result.compliance_flags.append(
            "REWRITE REQUIRED: HIPAA / 21 CFR Part 11 must be framed as 'designed to support', "
            "never as a flat compliant/certified claim. Do not send as-is."
        )
        result.verify_required = True
        result.verify_reason = "Non-approved compliance framing detected."

    # Rule 3: unverified cost figures
    if COST_FIGURE.search(answer):
        result.compliance_flags.append(
            "VERIFY: specific cost/savings figure detected. External use requires a verified, "
            "customer-approved reference. Replace with a bracketed placeholder if unverified."
        )
        result.verify_required = True
        if not result.verify_reason:
            result.verify_reason = "Unverified quantitative claim."

    # Rule 4: no approved source = mandatory verify flag
    approved_sources = [s for s, st in zip(source_ids, source_statuses) if st == "approved"]
    if not approved_sources:
        result.verify_required = True
        placeholder_sources = [s for s, st in zip(source_ids, source_statuses) if st == "placeholder"]
        if placeholder_sources:
            result.verify_reason = (
                f"Answer draws on placeholder (unapproved) library entries: {', '.join(placeholder_sources)}. "
                "NOT IN APPROVED LIBRARY - VERIFY before sending."
            )
        else:
            result.verify_reason = (
                "NOT IN LIBRARY - no approved source found. Verify with the answer owner before sending."
            )

    return result
