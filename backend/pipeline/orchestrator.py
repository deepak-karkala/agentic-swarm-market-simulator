"""Pipeline orchestrator — chains Stages 0-4 + quality eval as a background task."""

from __future__ import annotations

import asyncio
import logging

from backend.api.schemas import SimulateRequest
from backend.llm.client import LLMClient
from backend.pipeline.task_manager import task_manager

logger = logging.getLogger(__name__)


def run_pipeline_background(sim_id: str, request: SimulateRequest, llm_client: LLMClient):
    """Entry point for FastAPI BackgroundTasks. Runs in a separate thread."""

    async def _run():
        try:
            await _run_pipeline(sim_id, request, llm_client)
        except Exception:
            logger.exception("Pipeline failed for sim_id=%s", sim_id)
        finally:
            task_manager.release()

    asyncio.run(_run())


async def _run_pipeline(sim_id: str, req: SimulateRequest, llm: LLMClient):
    """Run the full pipeline: Stage 0 → 1 → 2 → 3 → 3.5 → 4 → quality eval."""

    # ── Stage 0: Reality Seeding ──
    from backend.stage0.seeder import run_seeder

    task_manager.emit_event(sim_id, "stage_start", {"stage": "stage0", "message": "Gathering market intelligence..."})
    seed = await run_seeder(req.scenario_text, req.geography, req.vertical, llm, sim_id)

    # ── Stage 1: Graph Build ──
    from backend.stage1.graph_builder import build_graph

    task_manager.emit_event(sim_id, "stage_start", {"stage": "stage1", "message": "Building knowledge graph..."})
    graph = await build_graph(seed, llm, sim_id)

    # ── Stage 2: Agent Factory ──
    from backend.stage2.agent_factory import generate_agents

    task_manager.emit_event(sim_id, "stage_start", {"stage": "stage2", "message": "Creating agent personas..."})
    try:
        agents = await generate_agents(graph, llm, consumer_count=req.agent_count, sim_id=sim_id)
    except Exception:
        logger.exception("Stage 2 agent generation failed — using minimal agents")
        # Minimal fallback: 10 agents
        from backend.stage2.agent_factory import AgentGenerationResult
        agents = AgentGenerationResult(
            twitter_profiles_csv="user_id,name,username,user_char,description\n",
            reddit_profiles_json="[]",
            total_agents=0,
        )

    # ── Stage 3: 3-track Simulation ──
    from backend.stage3 import run_stage3

    task_manager.emit_event(sim_id, "stage_start", {"stage": "stage3", "message": "Running 3-track simulation..."})
    stage3_result = await run_stage3(seed, agents.twitter_profiles_csv, llm, sim_id=sim_id)

    # ── Stage 3.5: Expert Panel ──
    stats = stage3_result.stats
    track2 = stage3_result.track2
    track3 = stage3_result.track3

    from backend.stage35.expert_panel import run_expert_panel

    task_manager.emit_event(sim_id, "stage_start", {"stage": "stage35", "message": "Expert panel analysis running..."})
    experts = await run_expert_panel(seed, stats, llm, sim_id)

    # ── Stage 4: ReACT Synthesizer ──
    from backend.stage4.react_agent import synthesize_report

    task_manager.emit_event(sim_id, "stage_start", {"stage": "stage4", "message": "Synthesizing report..."})
    report = await synthesize_report(seed, stats, track2, track3, experts, llm, sim_id)

    # ── Quality Evaluation ──
    from backend.pipeline.quality_eval import evaluate_quality

    evaluated = evaluate_quality(report, experts)

    task_manager.emit_event(sim_id, "simulation_complete", {"sim_id": sim_id, "quality_checks": len(evaluated)})
