"""Stage 0: Reality Seeding — 6 parallel Tavily search + LLM parsing pipelines."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

from tavily import TavilyClient

from backend.llm.client import LLMClient, ModelTier

logger = logging.getLogger(__name__)

PIPELINES = [
    ("competitors", "{scenario} competitors market share"),
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

_LIST_PIPELINES = {"competitors", "historical_precedents", "regulatory", "kols"}
_DICT_PIPELINES = {"geo_context", "macro"}

DEFAULT_TIMEOUT = 120.0


@dataclass
class RealitySeed:
    """Output of Stage 0. Maps directly to reality_seed.json schema."""

    geography: str
    vertical: str
    scenario: str
    competitors: list[dict] = field(default_factory=list)
    historical_precedents: list[dict] = field(default_factory=list)
    geo_context: dict = field(default_factory=dict)
    regulatory: list[dict] = field(default_factory=list)
    kols: list[dict] = field(default_factory=list)
    macro: dict = field(default_factory=dict)
    gaps: list[str] = field(default_factory=list)
    confidence: dict[str, str] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return all(
            len(getattr(self, field)) == 0
            for field in [
                "competitors",
                "historical_precedents",
                "geo_context",
                "regulatory",
                "kols",
                "macro",
            ]
        )


def _safe_json_parse(raw: str, field: str) -> dict | list | None:
    """Parse LLM output as JSON, validating type matches pipeline contract."""
    try:
        data = json.loads(raw)
        if field in _LIST_PIPELINES and not isinstance(data, list):
            return None
        if field in _DICT_PIPELINES and not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, TypeError):
        return None


async def _run_pipeline(
    name: str,
    query: str,
    llm: LLMClient,
) -> tuple[str, dict | list | None, str]:
    """Run a single search pipeline. Returns (name, parsed_data, confidence)."""
    field = FIELD_MAP[name]
    try:
        client = TavilyClient()
        resp = await asyncio.to_thread(
            client.search, query=query, search_depth="basic", max_results=3,
        )
        results = resp.get("results", [])

        if not results:
            return name, None, "low"

        raw = json.dumps(results, default=str)
        prompt = (
            f"Parse these search results into a concise JSON summary "
            f"for the '{name}' pipeline. Return valid JSON only.\n\n{raw}"
        )
        parsed_raw = await llm.complete(prompt, tier=ModelTier.HAIKU)
        parsed = _safe_json_parse(parsed_raw, field)

        confidence = "high" if len(results) >= 2 else "medium"
        if parsed is None:
            return name, None, "low"

        return name, parsed, confidence

    except Exception:
        logger.exception("Pipeline '%s' failed", name)
        return name, None, "low"


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

    year = str(datetime.now().year)
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
        seed.confidence = {name: "low" for name, _ in PIPELINES}
        if sim_id:
            task_manager.emit_event(
                sim_id, "stage_complete",
                {"stage": "stage0", "duration_s": timeout, "gaps": seed.gaps, "confidence": seed.confidence},
            )
        return seed

    seed = RealitySeed(geography=geography, vertical=vertical, scenario=scenario)

    for (pipeline_name, _), result in zip(PIPELINES, gathered):
        field = FIELD_MAP[pipeline_name]

        if isinstance(result, Exception):
            logger.warning("Pipeline '%s' raised: %s", pipeline_name, result)
            seed.gaps.append(pipeline_name)
            seed.confidence[pipeline_name] = "low"
            continue

        name, data, confidence = result
        seed.confidence[pipeline_name] = confidence

        if data is not None:
            setattr(seed, field, data)
        else:
            seed.gaps.append(pipeline_name)

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_complete",
            {"stage": "stage0", "duration_s": 0, "gaps": seed.gaps, "confidence": seed.confidence},
        )

    return seed
