"""Stage 0: Reality Seeding — 6 parallel Tavily search + LLM parsing pipelines."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from tavily import TavilyClient

from backend.llm.client import LLMClient, ModelTier

logger = logging.getLogger(__name__)

PIPELINES = [
    ("competitors", "{scenario} competitors market share {year}"),
    ("historical", "{vertical} market disruption historical precedents"),
    ("geographic", "{geography} {vertical} consumer behavior trends"),
    ("regulatory", "{geography} {vertical} regulatory environment policies"),
    ("kols", "{vertical} key opinion leaders analysts influencers"),
    ("macro", "{geography} economic conditions interest rates consumer confidence"),
]

FIELD_MAP: dict[str, str] = {
    "competitors": "competitors",
    "historical": "historical_precedents",
    "geographic": "geo_context",
    "regulatory": "regulatory",
    "kols": "kols",
    "macro": "macro",
}
DEFAULT_TIMEOUT = 120.0


@dataclass
class RealitySeed:
    """Output of Stage 0. Maps directly to reality_seed.json schema."""

    geography: str
    vertical: str
    scenario: str
    competitors: str | list = "unavailable"
    historical_precedents: str | list = "unavailable"
    geo_context: str | dict = "unavailable"
    regulatory: str | list = "unavailable"
    kols: str | list = "unavailable"
    macro: str | dict = "unavailable"
    gaps: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return all(
            getattr(self, field) == "unavailable"
            for field in [
                "competitors",
                "historical_precedents",
                "geo_context",
                "regulatory",
                "kols",
                "macro",
            ]
        )


async def _run_pipeline(
    name: str,
    query: str,
    llm: LLMClient,
) -> dict:
    """Run a single search pipeline: Tavily search → LLM parse → structured dict."""
    try:
        client = TavilyClient()
        resp = await asyncio.to_thread(client.search, query=query, search_depth="basic", max_results=3)
        results = resp.get("results", [])

        if not results:
            return {name: "unavailable", "confidence": "low"}

        raw = json.dumps(results, default=str)
        prompt = (
            f"Parse these search results into a concise JSON summary "
            f"for the '{name}' pipeline. Return valid JSON only.\n\n{raw}"
        )
        parsed = await llm.complete(prompt, tier=ModelTier.HAIKU)
        return {name: parsed, "confidence": "high" if len(results) >= 2 else "medium"}

    except Exception:
        logger.exception("Pipeline '%s' failed", name)
        return {name: "unavailable", "confidence": "low"}


async def run_seeder(
    scenario: str,
    geography: str,
    vertical: str,
    llm: LLMClient,
    sim_id: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> RealitySeed:
    """Run all 6 search pipelines in parallel. Partial failure allowed."""
    from backend.pipeline.task_manager import task_manager

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_start",
            {"stage": "stage0", "message": "Gathering market intelligence..."},
        )

    year = "2025"
    tasks = []
    for name, template in PIPELINES:
        query = template.format(scenario=scenario, geography=geography, vertical=vertical, year=year)
        tasks.append(_run_pipeline(name, query, llm))

    try:
        gathered = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Stage 0 timed out after %.1fs", timeout)
        seed = RealitySeed(geography=geography, vertical=vertical, scenario=scenario)
        seed.gaps = [name for name, _ in PIPELINES]
        if sim_id:
            task_manager.emit_event(
                sim_id, "stage_complete",
                {"stage": "stage0", "duration_s": timeout, "gaps": seed.gaps},
            )
        return seed

    seed = RealitySeed(geography=geography, vertical=vertical, scenario=scenario)

    for (pipeline_name, _), result in zip(PIPELINES, gathered):
        field = FIELD_MAP[pipeline_name]
        if isinstance(result, Exception):
            logger.warning("Pipeline '%s' raised: %s", pipeline_name, result)
            seed.gaps.append(pipeline_name)
        elif isinstance(result, dict) and result.get(pipeline_name) != "unavailable":
            setattr(seed, field, result[pipeline_name])
        else:
            seed.gaps.append(pipeline_name)

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_complete",
            {"stage": "stage0", "duration_s": 0, "gaps": seed.gaps},
        )

    return seed
