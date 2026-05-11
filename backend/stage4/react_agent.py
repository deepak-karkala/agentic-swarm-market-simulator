"""Stage 4: ReACT Synthesizer — assembles simulation outputs into a 10-section report.

Guarantees every section is present in the returned dict.
Does NOT guarantee section-specific schema (that is a future enhancement).
Follows report format spec: ideation/report_format_spec.md
"""

from __future__ import annotations

import json
import logging

from backend.llm.client import LLMClient, ModelTier
from backend.pipeline.sim_stats import SimulationStats
from backend.stage0.seeder import RealitySeed
from backend.stage3.track2_boardroom import BoardroomResult
from backend.stage3.track3_analyst import AnalystReport
from backend.stage35.expert_panel import ExpertAnalysis

logger = logging.getLogger(__name__)

PLACEHOLDER = "[Section]: Insufficient simulation data. Consider increasing agent count or simulation rounds."

SECTIONS = [
    ("executive_summary", "Executive Summary"),
    ("public_narrative", "Public Narrative & Sentiment"),
    ("competitive_response", "Competitive Response Forecast"),
    ("financial_impact", "Financial Market Impact"),
    ("consumer_adoption", "Consumer Adoption Projection"),
    ("strategic_recommendations", "Strategic Recommendations"),
    ("competitive_landscape", "Competitive Landscape"),
    ("regulatory", "Regulatory Tailwinds/Headwinds"),
    ("kol_impact", "KOL & Influencer Impact"),
    ("methodology", "Methodology & Calibration"),
]


async def synthesize_report(
    seed: RealitySeed,
    stats: SimulationStats | None,
    track2: BoardroomResult | None,
    track3: list[AnalystReport] | None,
    experts: dict[str, ExpertAnalysis] | None,
    llm: LLMClient,
    sim_id: str | None = None,
) -> dict[str, str]:
    """Produce a 10-section report. Never returns a section silently absent."""
    from backend.pipeline.task_manager import task_manager

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_start",
            {"stage": "stage4", "message": "Synthesizing report..."},
        )

    report: dict[str, str] = {}
    for section_key, section_name in SECTIONS:
        content = await _generate_section(
            section_key, section_name, seed, stats, track2, track3, experts, llm,
        )
        report[section_key] = content

        if sim_id:
            task_manager.emit_event(
                sim_id, "section_complete",
                {"section": section_key, "name": section_name},
            )

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_complete",
            {"stage": "stage4", "sections": len(report)},
        )

    return report


async def _generate_section(
    key: str,
    name: str,
    seed: RealitySeed,
    stats: SimulationStats | None,
    track2: BoardroomResult | None,
    track3: list[AnalystReport] | None,
    experts: dict[str, ExpertAnalysis] | None,
    llm: LLMClient,
) -> str:
    prompt = _build_section_prompt(key, name, seed, stats, track2, track3, experts)

    # First attempt
    try:
        raw = await llm.complete(prompt, tier=ModelTier.SONNET, max_tokens=4096)
        if raw and raw.strip():
            return raw.strip()
    except Exception:
        logger.exception("Section '%s' LLM call failed — retrying", name)

    # Retry with broader query
    try:
        raw = await llm.complete(
            prompt + "\n\nProvide any available analysis for this section.",
            tier=ModelTier.SONNET,
            max_tokens=4096,
        )
        if raw and raw.strip():
            return raw.strip()
    except Exception:
        logger.exception("Section '%s' retry also failed — using placeholder", name)

    return PLACEHOLDER


def _build_section_prompt(
    key: str,
    name: str,
    seed: RealitySeed,
    stats: SimulationStats | None,
    track2: BoardroomResult | None,
    track3: list[AnalystReport] | None,
    experts: dict[str, ExpertAnalysis] | None,
) -> str:
    base = (
        f"You are writing a professional business impact report section.\n"
        f"Scenario: {seed.scenario}\n"
        f"Geography: {seed.geography}\n"
        f"Industry: {seed.vertical}\n\n"
        f"Write the '{name}' section.\n\n"
    )

    if key == "executive_summary":
        base += (
            "Provide a verdict (BEARISH/NEUTRAL/BULLISH), horizon estimate, "
            "and 3-5 bullet-point key findings. Include an aggregated confidence level. "
            "Write 2-3 paragraphs of professional analysis."
        )
    elif key == "public_narrative":
        base += (
            "Summarize the public narrative and sentiment arc across simulation rounds. "
            f"Data: {_fmt_stats(stats)}. "
            "Identify dominant narrative threads, key inflection points, and agent-group breakdowns."
        )
    elif key == "competitive_response":
        if track2 and track2.decisions:
            base += (
                "Forecast competitor responses based on boardroom simulation. "
                f"Decisions: {_fmt_decisions(track2)}. "
                "If boardroom data unavailable, note this and base analysis on Stage 0 context."
            )
        else:
            base += (
                "Boardroom simulation data unavailable — competitor response analysis "
                "is based on historical patterns from Stage 0 context only."
            )
    elif key == "financial_impact":
        base += (
            "Analyze financial market impact direction (no exact numbers). "
            f"Analyst reports: {_fmt_track3(track3)}. "
            "Discuss earnings revision direction, price target revision direction, and thesis shifts."
        )
    elif key == "consumer_adoption":
        base += (
            "Project consumer adoption curve position. "
            f"Adoption data: {_fmt_stats(stats)}. "
            "Break down by early adopters, mainstream, and laggard segments. "
            "Label as 'indicative' — this is a behavioral proxy."
        )
    elif key == "strategic_recommendations":
        base += (
            "Provide 3-5 actionable strategic recommendations. "
            "Tag each with persona (Strategy Exec, PM, Investor). "
            "Include timeline (immediate/near-term/strategic) and risk caveats. "
            "Base on the simulation signals, competitive response, and adoption data."
        )
    elif key == "competitive_landscape":
        expert_data = _fmt_expert(experts, "competitive") if experts else "Expert unavailable."
        base += (
            "Assess the current competitive landscape and moat positions. "
            f"Competitors: {json.dumps(seed.competitors, default=str)}. "
            f"Expert analysis: {expert_data}. "
            "Use Porter's Five Forces lens. Identify which competitor poses the greatest threat."
        )
    elif key == "regulatory":
        expert_data = _fmt_expert(experts, "regulatory") if experts else "Expert unavailable."
        base += (
            "Analyze regulatory tailwinds and headwinds. "
            f"Regulatory data: {json.dumps(seed.regulatory, default=str)}. "
            f"Expert analysis: {expert_data}. "
            "Discuss enforcement probability, compliance timelines, and policy impact."
        )
    elif key == "kol_impact":
        expert_data = _fmt_expert(experts, "consumer") if experts else "Expert unavailable."
        base += (
            "Analyze KOL and influencer impact on the scenario narrative. "
            f"KOL data: {json.dumps(seed.kols, default=str)}. "
            f"Expert analysis: {expert_data}. "
            "Identify top 3-5 KOLs, their likely stances, and amplification risk."
        )
    elif key == "methodology":
        base += (
            "Document the simulation methodology. Include: simulation parameters "
            f"(rounds: {stats.total_rounds if stats else 'N/A'}), "
            f"data sources from Stage 0, which expert agents contributed, "
            "known limitations (simulation not reality, directional signals only), "
            "and calibration score if available."
        )

    return base


def _fmt_stats(stats: SimulationStats | None) -> str:
    if stats is None:
        return "Unavailable."
    return json.dumps({
        "rounds": stats.total_rounds,
        "adoption": stats.adoption_proxy,
        "agents": stats.agent_group_summary,
    }, default=str)


def _fmt_decisions(track2: BoardroomResult) -> str:
    if not track2 or not track2.decisions:
        return "None."
    return json.dumps([{
        "competitor": d.competitor,
        "action": d.action_type,
        "timeline": d.timeline,
        "rationale": d.stated_rationale,
    } for d in track2.decisions], default=str)


def _fmt_track3(track3: list[AnalystReport] | None) -> str:
    if not track3:
        return "None."
    return json.dumps([{
        "analyst": r.analyst_name,
        "firm": r.firm,
        "target": r.target_company,
        "earnings_revision": r.earnings_revision_pct,
        "price_target_revision": r.price_target_revision_pct,
        "conviction": r.conviction,
    } for r in track3], default=str)


def _fmt_expert(experts: dict[str, ExpertAnalysis] | None, name: str) -> str:
    if not experts or name not in experts:
        return "Unavailable."
    e = experts[name]
    return json.dumps({
        "summary": e.summary,
        "key_findings": e.key_findings,
        "confidence": e.confidence,
    }, default=str)
