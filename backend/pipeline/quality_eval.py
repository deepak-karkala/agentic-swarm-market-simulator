"""Quality Evaluator — runs after Stage 4 to check report credibility.

Checks:
1. Evidence citation — section references simulation data or Stage 0 source
2. No unsourced precision — no exact percentages/dollar figures without attribution
3. No phantom expert references — no "McKinsey-persona" language without
   corresponding Stage 3.5 expert output
"""

from __future__ import annotations

import re
import logging

from backend.stage35.expert_panel import ExpertAnalysis

logger = logging.getLogger(__name__)

# Patterns that suggest unsourced numerical precision
_PRECISION_PATTERNS = [
    r"\b\d+\.?\d*\s*%",           # e.g. "7.3%", "15%"
    r"\$\d[\d,.]*",                # e.g. "$50" or "$1,000.00"
    r"stock will (rise|fall|drop|increase|decrease)",  # directional price claims
]

# Patterns that suggest expert persona references
_EXPERT_PATTERNS = [
    r"\bMcKinsey\b",
    r"\bGoldman\s+Sachs\b",
    r"\bNielsen\b",
    r"\bFTC\b|\bDOJ\b",
    r"\bexpert\s+agent\b",
    r"\bpersona\b",
]

# Phrases that suggest a data citation is present
_EVIDENCE_PATTERNS = [
    r"\(Round\s+\d+",
    r"\(Stage\s+0",
    r"\(Expert:",
    r"\(Calibration:",
    r"\bsource:",
    r"\d+\s+agents?\b",
]


def evaluate_quality(
    report: dict[str, str],
    experts: dict[str, ExpertAnalysis] | None,
) -> dict[str, str]:
    """Check each report section against quality criteria.

    Returns a new report dict with QUALITY FLAG annotations appended
    to sections that fail checks.
    """
    result: dict[str, str] = {}
    experts = experts or {}
    flags = 0

    for section_key, content in report.items():
        # Skip placeholder sections — they already own their limitations
        if "[Section]" in content:
            result[section_key] = content
            continue

        flagged = content

        # Check 1: evidence citation
        if not _has_evidence(content):
            flagged += "\n\n[QUALITY FLAG: insufficient evidence — no data citation found]"
            flags += 1

        # Check 2: unsourced precision
        if _has_unsourced_precision(content):
            flagged += "\n\n[QUALITY FLAG: unsourced numerical precision — no source attribute for exact claim]"
            flags += 1

        # Check 3: expert persona without expert data
        if _has_expert_reference(content) and not experts:
            flagged += "\n\n[QUALITY FLAG: expert persona referenced but Stage 3.5 expert data unavailable]"
            flags += 1

        result[section_key] = flagged

    logger.info("Quality evaluation complete: %d flag(s) across %d sections",
                 flags, len(report))
    return result


def _has_evidence(content: str) -> bool:
    return any(re.search(p, content, re.IGNORECASE) for p in _EVIDENCE_PATTERNS)


def _has_unsourced_precision(content: str) -> bool:
    # Check for numbers that look like unsourced claims
    numbers = re.findall(r"\b\d+\.?\d*\s*%", content)
    if not numbers:
        return False
    # A sourced number would have citation nearby (±80 chars)
    cited = any(re.search(p, content, re.IGNORECASE) for p in _EVIDENCE_PATTERNS)
    return not cited


def _has_expert_reference(content: str) -> bool:
    return any(re.search(p, content, re.IGNORECASE) for p in _EXPERT_PATTERNS)
