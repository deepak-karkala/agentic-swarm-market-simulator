"""Quality Evaluator — runs after Stage 4 to check report credibility.

Checks:
1. Evidence citation — section references simulation data or Stage 0 source
2. No unsourced precision — no exact percentages/dollar figures without
   a nearby citation (within 120 chars of the match)
3. No phantom expert references — expert persona language requires the
   corresponding Stage 3.5 expert to exist and have confidence != "low"
"""

from __future__ import annotations

import re
import logging

from backend.stage35.expert_panel import ExpertAnalysis

logger = logging.getLogger(__name__)

# Patterns for unsourced numerical precision
_PRECISION_PATTERNS = [
    (r"\b\d+\.?\d*\s*%", "percentage"),
    (r"\$\d[\d,.]*", "dollar"),
    (r"stock will (rise|fall|drop|increase|decline|decline|plunge|surge)", "stock_direction"),
    (r"share\s+price\s+(will|may|could)\s+(rise|fall|drop|decline|increase|decrease)", "stock_direction"),
]

# Patterns that suggest a data citation is nearby
_EVIDENCE_PATTERNS = [
    r"\(Round\s+\d+",
    r"\(Stage\s+0",
    r"\(Expert:",
    r"\(Calibration:",
    r"\bsource:",
    r"\d+\s+agents?\b",
]

# Expert reference → required expert key mapping
_EXPERT_REF_MAP: dict[str, str] = {
    "McKinsey": "competitive",
    "competitive strategy": "competitive",
    "porter": "competitive",
    "Goldman Sachs": "economic",
    "economist": "economic",
    "Nielsen": "consumer",
    "consumer behavior": "consumer",
    "FTC": "regulatory",
    "DOJ": "regulatory",
    "regulatory": "regulatory",
    "domain expert": "domain",
    "expert agent": None,   # generic — flag if no experts at all
    "persona": None,
}

CITATION_PROXIMITY = 120  # chars


def evaluate_quality(
    report: dict[str, str],
    experts: dict[str, ExpertAnalysis] | None,
) -> dict[str, str]:
    """Check each report section against quality criteria."""
    result: dict[str, str] = {}
    experts = experts or {}
    flags = 0

    for section_key, content in report.items():
        if "[Section]" in content:
            result[section_key] = content
            continue

        flagged = content

        if not _has_evidence(content):
            flagged += "\n\n[QUALITY FLAG: insufficient evidence — no data citation found]"
            flags += 1

        if _find_unsourced_precision(content):
            flagged += "\n\n[QUALITY FLAG: unsourced numerical precision — no source attribute near exact claim]"
            flags += 1

        if _has_unmatched_expert_ref(content, experts):
            flagged += "\n\n[QUALITY FLAG: expert persona referenced but corresponding Stage 3.5 expert data unavailable]"
            flags += 1

        result[section_key] = flagged

    logger.info("Quality evaluation complete: %d flag(s) across %d sections",
                 flags, len(report))
    return result


def _has_evidence(content: str) -> bool:
    return any(re.search(p, content, re.IGNORECASE) for p in _EVIDENCE_PATTERNS)


def _find_unsourced_precision(content: str) -> bool:
    """Return True if any precision claim lacks a nearby citation."""
    for pattern, _kind in _PRECISION_PATTERNS:
        for match in re.finditer(pattern, content, re.IGNORECASE):
            start = max(0, match.start() - CITATION_PROXIMITY)
            end = min(len(content), match.end() + CITATION_PROXIMITY)
            window = content[start:end]
            if not any(re.search(p, window, re.IGNORECASE) for p in _EVIDENCE_PATTERNS):
                return True
    return False


def _has_unmatched_expert_ref(
    content: str,
    experts: dict[str, ExpertAnalysis],
) -> bool:
    """Return True if an expert reference requires an expert that is missing/low."""
    if not experts:
        # Any expert reference fails when no experts exist
        for pattern, _ in _EXPERT_REF_MAP.items():
            if re.search(rf"\b{re.escape(pattern)}\b", content, re.IGNORECASE):
                return True
        return False

    for ref_pattern, required_key in _EXPERT_REF_MAP.items():
        if not re.search(rf"\b{re.escape(ref_pattern)}\b", content, re.IGNORECASE):
            continue
        if required_key is None:
            continue  # generic patterns are ok if any experts exist
        if required_key not in experts:
            return True
        expert = experts[required_key]
        if expert.confidence == "low":
            return True

    return False
