"""Pipeline orchestrator — chains Stages 0-4 + quality eval as a background task."""

from __future__ import annotations

import asyncio
import logging

from backend.api.schemas import SimulateRequest
from backend.llm.client import LLMClient
from backend.pipeline.task_manager import task_manager

logger = logging.getLogger(__name__)

_FALLBACK_CSV = (
    "user_id,name,username,user_char,description\n"
    "0,BotAlpha,botalpha,Synthetic fallback agent.,Minimal agent cohort.\n"
    "1,BotBeta,botbeta,Synthetic fallback agent.,Minimal agent cohort.\n"
)


def run_pipeline_background(sim_id: str, request: SimulateRequest, llm_client: LLMClient):
    """Entry point for FastAPI BackgroundTasks. Runs in a separate thread."""

    async def _run():
        try:
            await _run_pipeline(sim_id, request, llm_client)
        except Exception:
            logger.exception("Pipeline failed for sim_id=%s", sim_id)
            task_manager.emit_event(
                sim_id, "simulation_error",
                {"sim_id": sim_id, "message": "Pipeline execution failed — see server logs."},
            )
        finally:
            task_manager.release()

    asyncio.run(_run())


async def _run_pipeline(sim_id: str, req: SimulateRequest, llm: LLMClient):
    """Run the full pipeline: Stage 0 → 1 → 2 → 3 → 3.5 → 4 → quality eval."""

    # ── Stage 0 ──
    from backend.stage0.seeder import run_seeder
    seed = await run_seeder(req.scenario_text, req.geography, req.vertical, llm, sim_id)

    # ── Stage 1 ──
    from backend.stage1.graph_builder import build_graph
    graph = await build_graph(seed, llm, sim_id)

    # ── Stage 2 ──
    from backend.stage2.agent_factory import AgentGenerationResult, generate_agents
    try:
        agents = await generate_agents(graph, llm, consumer_count=req.agent_count, sim_id=sim_id)
    except Exception:
        logger.exception("Stage 2 agent generation failed — using minimal fallback agents")
        agents = AgentGenerationResult(
            twitter_profiles_csv=_FALLBACK_CSV,
            reddit_profiles_json="[]",
            total_agents=2,
        )

    # ── Stage 3 ──
    from backend.stage3 import run_stage3
    stage3_result = await run_stage3(seed, agents.twitter_profiles_csv, llm, sim_id=sim_id)

    # ── Stage 3.5 ──
    from backend.stage35.expert_panel import run_expert_panel
    experts = await run_expert_panel(seed, stage3_result.stats, llm, sim_id)

    # ── Stage 4 ──
    from backend.stage4.react_agent import synthesize_report
    report = await synthesize_report(
        seed, stage3_result.stats, stage3_result.track2, stage3_result.track3, experts, llm, sim_id,
    )

    # ── Quality ──
    from backend.pipeline.quality_eval import evaluate_quality
    evaluated = evaluate_quality(report, experts)

    # Persist report
    task_manager.set_report(sim_id, evaluated)

    task_manager.emit_event(
        sim_id, "simulation_complete",
        {"sim_id": sim_id, "quality_checks": len(evaluated)},
    )
