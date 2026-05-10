"""Stage 3 Track 2: Boardroom competitive response simulation.

Phase 1 implementation: LLM-direct competitor deliberation with decision
parsing. CAMEL-AI RolePlaying integration is deferred to Phase 2 (see
risk register — Track 2 CAMEL init failure is high-probability/low-impact).

Output: boardroom_decisions.json — per-competitor strategic decisions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Literal

from backend.llm.client import LLMClient, ModelTier
from backend.stage0.seeder import RealitySeed

logger = logging.getLogger(__name__)

DecisionAction = Literal["price_cut", "product_launch", "partnership", "wait", "other"]
DecisionTimeline = Literal["immediate", "30_days", "90_days", "unclear"]
DecisionConfidence = Literal["high", "medium", "low"]

ALLOWED_ACTIONS: set[str] = {"price_cut", "product_launch", "partnership", "wait", "other"}
ALLOWED_TIMELINES: set[str] = {"immediate", "30_days", "90_days", "unclear"}
ALLOWED_CONFIDENCES: set[str] = {"high", "medium", "low"}

REQUIRED_DECISION_KEYS = {
    "competitor", "action_type", "timeline", "stated_rationale", "confidence",
}


@dataclass
class BoardroomDecision:
    competitor: str
    action_type: DecisionAction
    timeline: DecisionTimeline
    stated_rationale: str
    confidence: DecisionConfidence = "medium"


@dataclass
class BoardroomResult:
    status: str = "failed"  # completed | failed | timeout
    camel_used: bool = False  # True when CAMEL-AI RolePlaying was used (Phase 2)
    decisions: list[BoardroomDecision] = field(default_factory=list)
    decisions_json: str | None = None


async def run_track2(
    seed: RealitySeed,
    llm: LLMClient,
    sim_id: str | None = None,
    timeout: float = 1200.0,
) -> BoardroomResult:
    """Run boardroom deliberation. Phase 1 uses LLM-direct fallback.

    CAMEL-AI RolePlaying integration is planned for Phase 2.
    The guarded init ensures any failure returns cleanly without
    crashing the rest of Stage 3.
    """
    from backend.pipeline.task_manager import task_manager

    if sim_id:
        task_manager.emit_event(
            sim_id, "track_start",
            {"track": 2, "message": "Running boardroom simulation..."},
        )

    try:
        result = await asyncio.wait_for(
            _run_boardroom_deliberation(seed, llm),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Track 2 timed out after %.1fs", timeout)
        result = BoardroomResult(status="timeout")
    except Exception:
        logger.exception("Track 2 deliberation failed")
        result = BoardroomResult(status="failed")

    if sim_id:
        task_manager.emit_event(
            sim_id, "track_complete",
            {
                "track": 2,
                "status": result.status,
                "decisions": len(result.decisions),
                "camel_used": result.camel_used,
            },
        )

    return result


async def _run_boardroom_deliberation(
    seed: RealitySeed,
    llm: LLMClient,
) -> BoardroomResult:
    """Run LLM-direct competitor deliberation (Phase 1 fallback path)."""
    competitors = seed.competitors if isinstance(seed.competitors, list) else []
    if isinstance(competitors, dict):
        competitors = [competitors]
    if not competitors:
        competitors = [{"name": "Market Leader"}]

    decisions = []
    for comp in competitors[:3]:
        prompt = _build_competitor_prompt(seed, comp)
        raw = await llm.complete(prompt, tier=ModelTier.SONNET, max_tokens=2048)
        decision = _parse_decision(raw, comp.get("name", "Unknown"))
        if decision:
            decisions.append(decision)

    return BoardroomResult(
        status="completed",
        camel_used=False,
        decisions=decisions,
        decisions_json=json.dumps([d.__dict__ for d in decisions], default=str),
    )


def _build_competitor_prompt(seed: RealitySeed, competitor: dict) -> str:
    return (
        f"You are the C-suite leadership team of {competitor.get('name', 'a company')}. "
        f"Scenario: {seed.scenario}. "
        f"Industry: {seed.vertical}. Geography: {seed.geography}. "
        f"Market share: {competitor.get('market_share', 'unknown')}. "
        f"Decide the company's strategic response. Return valid JSON with keys: "
        f'competitor (string), action_type (one of: price_cut, product_launch, partnership, wait, other), '
        f'timeline (one of: immediate, 30_days, 90_days, unclear), '
        f'stated_rationale (string), confidence (one of: high, medium, low). '
        f"Return ONLY valid JSON, no other text."
    )


def _parse_decision(raw: str, company: str) -> BoardroomDecision | None:
    """Parse LLM output into a BoardroomDecision. Rejects invalid/missing fields."""
    try:
        data = json.loads(raw)
        # Inject company if LLM doesn't set it
        data.setdefault("competitor", company)
        # Require all expected keys
        missing = REQUIRED_DECISION_KEYS - set(data)
        if missing:
            logger.warning("Boardroom decision missing keys: %s", missing)
            return None
        if data["action_type"] not in ALLOWED_ACTIONS:
            logger.warning("Invalid action_type: %s", data["action_type"])
            return None
        if data["timeline"] not in ALLOWED_TIMELINES:
            logger.warning("Invalid timeline: %s", data["timeline"])
            return None
        if data.get("confidence", "medium") not in ALLOWED_CONFIDENCES:
            logger.warning("Invalid confidence: %s", data.get("confidence"))
            return None
        return BoardroomDecision(
            competitor=data["competitor"],
            action_type=data["action_type"],
            timeline=data["timeline"],
            stated_rationale=data["stated_rationale"],
            confidence=data.get("confidence", "medium"),
        )
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("Failed to parse boardroom decision: %s", e)
        return None
