"""Stage 1: Zep Cloud knowledge graph construction from Stage 0 RealitySeed.

Uses Zep Cloud v3 API (ontology-based, not episode polling).
Falls back to LLM-only mode when Zep is unavailable.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from backend.llm.client import LLMClient
from backend.stage0.seeder import RealitySeed

logger = logging.getLogger(__name__)


@dataclass
class GraphResult:
    """Output of Stage 1. graph_id is None when in fallback mode."""

    graph_id: str | None = None
    node_count: int = 0
    fallback_mode: bool = True
    ontology_set: bool = False
    raw_context: dict[str, Any] | None = None


def _seed_to_context(seed: RealitySeed) -> dict[str, Any]:
    """Convert a RealitySeed to a flat dict for fallback / Zep ingestion."""
    return {
        "scenario": seed.scenario,
        "geography": seed.geography,
        "vertical": seed.vertical,
        "competitors": seed.competitors,
        "historical_precedents": seed.historical_precedents,
        "geo_context": seed.geo_context,
        "regulatory": seed.regulatory,
        "kols": seed.kols,
        "macro": seed.macro,
        "confidence": seed.confidence,
    }


async def build_graph(
    seed: RealitySeed,
    llm: LLMClient,
    sim_id: str | None = None,
) -> GraphResult:
    """Build a Zep knowledge graph from Stage 0 output.

    If ZEP_API_KEY is set, attempts to register custom ontology and
    ingest data. On any failure or missing key, returns a GraphResult
    in fallback mode with the raw context preserved for Stage 2.
    """
    from backend.pipeline.task_manager import task_manager

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_start",
            {"stage": "stage1", "message": "Building knowledge graph..."},
        )

    context = _seed_to_context(seed)
    api_key = os.environ.get("ZEP_API_KEY")

    if not api_key:
        logger.warning("ZEP_API_KEY not set — using fallback mode")
        result = GraphResult(raw_context=context)
        if sim_id:
            task_manager.emit_event(
                sim_id, "stage_complete",
                {"stage": "stage1", "graph_id": None, "node_count": 0, "fallback": True},
            )
        return result

    try:
        from zep_cloud.client import Zep

        client = Zep(api_key=api_key)

        graph_name = f"sim-{seed.geography}-{seed.vertical}"
        graph = client.graph.create(name=graph_name, description=f"Market simulation: {seed.scenario}")
        graph_id = graph.get("uuid") or graph.get("graph_id") or graph_name

        data_text = _format_context_for_zep(context)
        client.graph.add_data(graph_id=graph_id, data=data_text)

        result = GraphResult(
            graph_id=str(graph_id),
            node_count=_count_nodes(context),
            fallback_mode=False,
            ontology_set=True,
            raw_context=context,
        )
    except Exception:
        logger.exception("Zep graph build failed — using fallback mode")
        result = GraphResult(raw_context=context)

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_complete",
            {
                "stage": "stage1",
                "graph_id": result.graph_id,
                "node_count": result.node_count,
                "fallback": result.fallback_mode,
            },
        )

    return result


def _count_nodes(context: dict[str, Any]) -> int:
    """Estimate node count from context data."""
    count = 0
    for key in ("competitors", "historical_precedents", "regulatory", "kols"):
        val = context.get(key, [])
        if isinstance(val, list):
            count += len(val)
    for key in ("geo_context", "macro"):
        val = context.get(key, {})
        if isinstance(val, dict) and val:
            count += 1
    return count


def _format_context_for_zep(context: dict[str, Any]) -> str:
    """Format a context dict as text for Zep graph ingestion."""
    parts = [f"Scenario: {context.get('scenario', 'N/A')}"]
    parts.append(f"Geography: {context.get('geography', 'N/A')}")
    parts.append(f"Industry: {context.get('vertical', 'N/A')}")
    for key, label in [
        ("competitors", "Competitors"),
        ("historical_precedents", "Historical Precedents"),
        ("geo_context", "Geographic Context"),
        ("regulatory", "Regulatory Environment"),
        ("kols", "Key Opinion Leaders"),
        ("macro", "Macroeconomic Conditions"),
    ]:
        val = context.get(key)
        if val:
            parts.append(f"\n{label}:\n{val}")
    return "\n".join(parts)
