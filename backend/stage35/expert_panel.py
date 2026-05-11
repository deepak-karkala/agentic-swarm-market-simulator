"""Stage 3.5: Expert Panel — 5 specialist agents interpret simulation output."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from backend.llm.client import LLMClient, ModelTier
from backend.pipeline.sim_stats import SimulationStats
from backend.stage0.seeder import RealitySeed

logger = logging.getLogger(__name__)


@dataclass
class ExpertAnalysis:
    summary: str = "Analysis unavailable — expert agent did not produce output."
    key_findings: list[str] = field(default_factory=list)
    confidence: str = "low"
    caveats: list[str] = field(default_factory=list)


_ALLOWED_CONFIDENCES = {"high", "medium", "low"}

EXPERTS = ["competitive", "economic", "consumer", "domain", "regulatory"]


def _make_placeholder() -> ExpertAnalysis:
    """Return a fresh placeholder (never share a mutable singleton)."""
    return ExpertAnalysis()


async def run_expert_panel(
    seed: RealitySeed,
    stats: SimulationStats | None,
    llm: LLMClient,
    sim_id: str | None = None,
    per_agent_timeout: float = 90.0,
) -> dict[str, ExpertAnalysis]:
    """Run 5 specialist expert agents in parallel."""
    from backend.pipeline.task_manager import task_manager

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_start",
            {"stage": "stage35", "message": "Expert panel analysis running..."},
        )

    context = {
        "scenario": seed.scenario,
        "geography": seed.geography,
        "vertical": seed.vertical,
        "competitors": seed.competitors,
        "regulatory": seed.regulatory,
        "kols": seed.kols,
        "macro": seed.macro,
        "stats_rounds": stats.total_rounds if stats else 0,
    }

    tasks = []
    for name in EXPERTS:
        tasks.append(_run_expert(name, context, stats, llm, per_agent_timeout))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    panel: dict[str, ExpertAnalysis] = {}
    for name, r in zip(EXPERTS, results):
        if isinstance(r, ExpertAnalysis):
            panel[name] = r
        else:
            logger.warning("Expert '%s' failed: %s", name, r)
            panel[name] = _make_placeholder()

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_complete",
            {
                "stage": "stage35",
                "experts_completed": sum(1 for a in panel.values() if a.confidence != "low"),
                "experts_total": len(EXPERTS),
            },
        )

    return panel


async def _run_expert(
    name: str,
    context: dict,
    stats: SimulationStats | None,
    llm: LLMClient,
    timeout: float,
) -> ExpertAnalysis:
    try:
        return await asyncio.wait_for(
            _call_expert(name, context, stats, llm),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Expert '%s' timed out after %.1fs", name, timeout)
        return _make_placeholder()
    except Exception:
        logger.exception("Expert '%s' failed", name)
        return _make_placeholder()


async def _call_expert(
    name: str,
    context: dict,
    stats: SimulationStats | None,
    llm: LLMClient,
) -> ExpertAnalysis:
    prompt = _build_expert_prompt(name, context, stats)
    raw = await llm.complete(prompt, tier=ModelTier.SONNET, max_tokens=4096)
    return _parse_expert_output(raw)


def _build_expert_prompt(name: str, context: dict, stats: SimulationStats | None) -> str:
    persona_map = {
        "competitive": (
            "You are a 15-year McKinsey partner and competitive strategy specialist. "
            "Analyze the competitive dynamics using Porter's Five Forces framework. "
            "Focus on how competitors will react, market entry playbooks, and competitive moats."
        ),
        "economic": (
            "You are a Goldman Sachs lead economist and macro-sector specialist. "
            "Analyze price elasticity, consumer spending cycles, category TAM trajectory, "
            "and macro regime implications from the simulation data."
        ),
        "consumer": (
            "You are a Nielsen/NielsenIQ VP with 20 years of consumer research experience. "
            "Analyze adoption curves (Rogers), brand loyalty erosion, segment-level price "
            "sensitivity, and consumer behavior patterns from the simulation."
        ),
        "domain": (
            "You are a senior industry analyst with 15 years of domain expertise in "
            f"{context.get('vertical', 'technology')}. "
            "Analyze domain-specific competitive dynamics, regulatory nuances, "
            "and category-specific patterns from the simulation data."
        ),
        "regulatory": (
            "You are a former FTC/DOJ attorney specializing in antitrust and market regulation. "
            "Analyze enforcement probability, regulatory timeline modeling, compliance cost "
            "estimates, and policy tailwinds/headwinds from the simulation and context data."
        ),
    }

    persona = persona_map.get(name, persona_map["domain"])
    prompt = (
        f"{persona}\n\n"
        f"Scenario: {context.get('scenario', 'N/A')}\n"
        f"Geography: {context.get('geography', 'N/A')}\n"
        f"Industry vertical: {context.get('vertical', 'N/A')}\n"
    )
    if stats:
        prompt += (
            f"\nSimulation Stats:\n"
            f"Total rounds: {stats.total_rounds}\n"
            f"Agent groups: {json.dumps(stats.agent_group_summary)}\n"
            f"Adoption proxy: {json.dumps(stats.adoption_proxy)}\n"
        )
    prompt += (
        f"\nContext data:\n"
        f"Competitors: {json.dumps(context.get('competitors', []), default=str)}\n"
        f"Regulatory: {json.dumps(context.get('regulatory', []), default=str)}\n"
        f"KOLs: {json.dumps(context.get('kols', []), default=str)}\n"
        f"Macro: {json.dumps(context.get('macro', {}), default=str)}\n"
        f"\nReturn a JSON object with exactly these keys: "
        f"summary (2-3 paragraphs of analysis), "
        f"key_findings (list of strings, 3-5 items), "
        f"confidence (one of: high, medium, low), "
        f"caveats (list of strings, any limitations or assumptions). "
        f"Return ONLY valid JSON, no other text."
    )
    return prompt


def _parse_expert_output(raw: str) -> ExpertAnalysis:
    try:
        data = json.loads(raw)

        # Require all expected keys
        required = {"summary", "key_findings", "confidence", "caveats"}
        missing = required - set(data)
        if missing:
            logger.warning("Expert output missing keys: %s", missing)
            return _make_placeholder()

        # Validate types
        if not isinstance(data["summary"], str):
            return _make_placeholder()
        if not isinstance(data["key_findings"], list):
            return _make_placeholder()
        if not isinstance(data["caveats"], list):
            return _make_placeholder()

        # Validate confidence
        confidence = data.get("confidence", "")
        if confidence not in _ALLOWED_CONFIDENCES:
            logger.warning("Expert output invalid confidence: %s", confidence)
            return _make_placeholder()

        return ExpertAnalysis(
            summary=data["summary"],
            key_findings=data["key_findings"],
            confidence=confidence,
            caveats=data["caveats"],
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        logger.warning("Expert output parse failed")
        return _make_placeholder()
