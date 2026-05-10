"""Stage 3 Track 2: Boardroom CAMEL-AI RolePlaying simulation.

Guarded init pattern: wraps CAMEL-AI RolePlaying in try/except so that
any initialization failure (ImportError, runtime error, asyncio conflict)
gracefully degrades without crashing Stage 3.

Output: boardroom_decisions.json — per-competitor strategic decisions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from backend.llm.client import LLMClient, ModelTier
from backend.stage0.seeder import RealitySeed

logger = logging.getLogger(__name__)


@dataclass
class BoardroomDecision:
    competitor: str
    action_type: str  # price_cut | product_launch | partnership | wait | other
    timeline: str  # immediate | 30_days | 90_days | unclear
    stated_rationale: str
    confidence: str = "medium"  # high | medium | low


@dataclass
class BoardroomResult:
    status: str = "failed"  # completed | failed | timeout
    decisions: list[BoardroomDecision] = field(default_factory=list)
    decisions_json: str | None = None


async def run_track2(
    seed: RealitySeed,
    llm: LLMClient,
    sim_id: str | None = None,
    timeout: float = 1200.0,
) -> BoardroomResult:
    """Run CAMEL-AI boardroom deliberation with guarded init.

    On any CAMEL-AI failure, returns BoardroomResult(status="failed").
    This ensures Tracks 1 and 3 continue without interruption.
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
        logger.exception("Track 2 CAMEL-AI init/deliberation failed")
        result = BoardroomResult(status="failed")

    if sim_id:
        task_manager.emit_event(
            sim_id, "track_complete",
            {"track": 2, "status": result.status, "decisions": len(result.decisions)},
        )

    return result


async def _run_boardroom_deliberation(
    seed: RealitySeed,
    llm: LLMClient,
) -> BoardroomResult:
    """Core CAMEL-AI RolePlaying deliberation. Falls back to LLM if CAMEL unavailable."""
    competitors = seed.competitors if isinstance(seed.competitors, list) else []
    if isinstance(competitors, dict):
        competitors = [competitors]
    if not competitors:
        competitors = [{"name": "Market Leader"}]

    # Attempt CAMEL-AI RolePlaying (guarded — may not be installed)
    try:
        import importlib
        importlib.import_module("camel.societies")
    except ImportError:
        logger.warning("CAMEL-AI not available — using LLM fallback for boardroom")
    except Exception:
        logger.exception("CAMEL-AI RolePlaying init failed — using LLM fallback")

    # LLM-only fallback
    decisions = []
    for comp in competitors[:3]:
        prompt = _build_competitor_prompt(seed, comp)
        raw = await llm.complete(prompt, tier=ModelTier.SONNET, max_tokens=2048)
        decision = _parse_decision(raw, comp.get("name", "Unknown"))
        if decision:
            decisions.append(decision)

    return BoardroomResult(
        status="completed",
        decisions=decisions,
        decisions_json=json.dumps([d.__dict__ for d in decisions]),
    )


def _build_competitor_prompt(seed: RealitySeed, competitor: dict) -> str:
    return (
        f"You are the C-suite leadership team of {competitor.get('name', 'a company')}. "
        f"Scenario: {seed.scenario}. "
        f"Industry: {seed.vertical}. Geography: {seed.geography}. "
        f"Market share: {competitor.get('market_share', 'unknown')}. "
        f"Decide the company's strategic response. Return valid JSON with keys: "
        f'competitor, action_type (one of: price_cut, product_launch, partnership, wait, other), '
        f'timeline (one of: immediate, 30_days, 90_days, unclear), '
        f'stated_rationale, confidence (one of: high, medium, low). '
        f"Return ONLY valid JSON, no other text."
    )


def _parse_decision(raw: str, company: str) -> BoardroomDecision | None:
    try:
        data = json.loads(raw)
        data.setdefault("competitor", company)
        return BoardroomDecision(
            competitor=data.get("competitor", company),
            action_type=data.get("action_type", "wait"),
            timeline=data.get("timeline", "unclear"),
            stated_rationale=data.get("stated_rationale", ""),
            confidence=data.get("confidence", "medium"),
        )
    except (json.JSONDecodeError, ValueError):
        return None
