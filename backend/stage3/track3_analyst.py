"""Stage 3 Track 3: Analyst Desk — sell-side analyst report generation."""

from __future__ import annotations

import asyncio
import json
import logging

from typing import Literal

from pydantic import BaseModel

from backend.llm.client import LLMClient, ModelTier
from backend.stage0.seeder import RealitySeed

logger = logging.getLogger(__name__)


class AnalystReport(BaseModel):
    analyst_name: str
    firm: str
    target_company: str
    earnings_revision_pct: float
    price_target_revision_pct: float
    thesis_update: str
    conviction: Literal["high", "medium", "low"]
    rating_change: Literal["upgrade", "downgrade", "maintain", "initiate"]


ANALYST_FIRMS = [
    "Goldman Sachs", "Morgan Stanley", "J.P. Morgan", "BofA Securities",
    "Citigroup", "Barclays", "UBS", "Deutsche Bank", "Credit Suisse", "Wells Fargo",
]


def _build_analyst_prompt(seed: RealitySeed, firm: str, idx: int) -> str:
    competitors = seed.competitors if isinstance(seed.competitors, list) else []
    target = competitors[0]["name"] if competitors else "the market leader"
    macro = seed.macro if isinstance(seed.macro, dict) else {}
    return (
        f"You are a sell-side equity analyst at {firm} covering the "
        f"{seed.vertical} sector in {seed.geography}. "
        f"Scenario: {seed.scenario}. "
        f"Target company: {target}. "
        f"Macro context: {json.dumps(macro)}. "
        f"Competitors: {json.dumps(competitors[:3])}. "
        f"Generate a structured analyst report as valid JSON with exactly these keys: "
        f'analyst_name, firm, target_company, earnings_revision_pct, '
        f'price_target_revision_pct, thesis_update, conviction, rating_change. '
        f"conviction must be one of: high, medium, low. "
        f"rating_change must be one of: upgrade, downgrade, maintain, initiate. "
        f"earnings_revision_pct and price_target_revision_pct are floats "
        f"(positive or negative). Return ONLY valid JSON, no other text."
    )


REQUIRED_REPORT_KEYS = {
    "analyst_name", "target_company", "earnings_revision_pct",
    "price_target_revision_pct", "thesis_update", "conviction", "rating_change",
}


def _parse_report(raw: str, firm: str) -> AnalystReport | None:
    try:
        data = json.loads(raw)
        # firm is injected by us, not expected from LLM
        data["firm"] = firm
        # Reject if any required key is missing from the LLM response
        missing = REQUIRED_REPORT_KEYS - set(data)
        if missing:
            logger.warning("Analyst report missing required keys: %s", missing)
            return None
        return AnalystReport(**data)
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("Failed to parse analyst report: %s", e)
        return None


async def _generate_one(
    llm: LLMClient,
    seed: RealitySeed,
    firm: str,
    idx: int,
    sem: asyncio.Semaphore,
) -> AnalystReport | None:
    async with sem:
        prompt = _build_analyst_prompt(seed, firm, idx)

        # First attempt
        raw = await llm.complete(prompt, tier=ModelTier.SONNET)
        report = _parse_report(raw, firm)
        if report is not None:
            return report

        # Retry with explicit schema reminder
        retry_prompt = (
            f"{prompt}\n\nYOUR PREVIOUS RESPONSE WAS INVALID JSON. "
            f"You MUST return ONLY a valid JSON object with the exact keys specified."
        )
        raw = await llm.complete(retry_prompt, tier=ModelTier.SONNET)
        return _parse_report(raw, firm)


async def generate_analyst_reports(
    seed: RealitySeed,
    llm: LLMClient,
    analyst_count: int = 10,
    sim_id: str | None = None,
) -> list[AnalystReport]:
    """Generate sell-side analyst reports in parallel."""
    from backend.pipeline.task_manager import task_manager

    if sim_id:
        task_manager.emit_event(
            sim_id, "track_start",
            {"track": 3, "message": "Running analyst desk..."},
        )

    sem = asyncio.Semaphore(5)

    tasks = []
    for i in range(analyst_count):
        firm = ANALYST_FIRMS[i % len(ANALYST_FIRMS)]
        tasks.append(_generate_one(llm, seed, firm, i, sem))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    reports: list[AnalystReport] = []
    for r in results:
        if isinstance(r, AnalystReport):
            reports.append(r)
        elif isinstance(r, Exception):
            logger.warning("Analyst generation raised: %s", r)

    if sim_id:
        task_manager.emit_event(
            sim_id, "track_complete",
            {"track": 3, "reports_generated": len(reports)},
        )

    return reports
