"""Stage 3 Track 1: OASIS Twitter Social Simulation.

Runs OASIS in-process (not subprocess), tracking rounds externally
and exporting SQLite output to actions.jsonl with injected round field.

Source: https://docs.oasis.camel-ai.org — OASIS runs via env.step() loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

from backend.llm.client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class Track1Result:
    status: str = "failed"  # completed | failed | timeout
    actions_jsonl_path: str | None = None
    rounds: int = 0


async def run_track1(
    twitter_profiles_csv: str,
    llm: LLMClient,
    rounds: int = 10,
    agent_count: int = 100,
    sim_id: str | None = None,
    timeout: float = 1200.0,
) -> Track1Result:
    """Run OASIS Twitter simulation with round tracking and JSONL export.

    - Launches OASIS in-process via env.step() loop
    - Tracks rounds externally (OASIS SQLite has no round column)
    - Exports post + trace tables to actions.jsonl with round field
    - Hard timeout via asyncio.wait_for
    """
    from backend.pipeline.task_manager import task_manager

    if sim_id:
        task_manager.emit_event(
            sim_id, "track_start",
            {"track": 1, "message": "Running public narrative simulation...", "agents": agent_count},
        )

    try:
        result = await asyncio.wait_for(
            _run_oasis_simulation(twitter_profiles_csv, agent_count, rounds, sim_id),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Track 1 timed out after %.1fs", timeout)
        result = Track1Result(status="timeout")
        if sim_id:
            task_manager.emit_event(sim_id, "track_complete", {"track": 1, "status": "timeout"})
        return result

    if sim_id:
        task_manager.emit_event(
            sim_id, "track_complete",
            {"track": 1, "status": result.status, "rounds": result.rounds},
        )

    return result


async def _run_oasis_simulation(
    profiles_csv: str,
    agent_count: int,
    rounds: int,
    sim_id: str | None,
) -> Track1Result:
    """Core OASIS simulation loop with round tracking."""
    # Lazy imports — OASIS loads Twhin-BERT which is slow
    from camel.configs import AnthropicConfig
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType, ModelType
    from oasis import ActionType, LLMAction, ManualAction, generate_twitter_agent_graph
    import oasis

    twitter_actions = ActionType.get_default_twitter_actions()
    from backend.pipeline.task_manager import task_manager

    # Build a Camel model from the LLM client's API key
    import os
    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("No API key available for OASIS simulation")

    # Use OpenAI-compatible path for DeepSeek, direct Anthropic otherwise
    if os.environ.get("DEEPSEEK_API_KEY"):
        model = ModelFactory.create(
            model_platform=ModelPlatformType.OPENAI_COMPATIBLE_MODEL,
            model_type="deepseek-chat",
            api_key=api_key,
            url="https://api.deepseek.com/v1",
            model_config_dict={"temperature": 0.7},
        )
    else:
        model = ModelFactory.create(
            model_platform=ModelPlatformType.ANTHROPIC,
            model_type=ModelType.CLAUDE_3_HAIKU,
            model_config_dict=AnthropicConfig(temperature=0.7).as_dict(),
        )

    # Write CSV to temp file for OASIS ingestion
    tmpdir = Path(tempfile.mkdtemp(prefix="oasis_track1_"))
    try:
        csv_path = tmpdir / "twitter_profiles.csv"
        csv_path.write_text(profiles_csv)
        db_path = tmpdir / "twitter_simulation.db"
        if db_path.exists():
            db_path.unlink()

        agent_graph = await generate_twitter_agent_graph(
            profile_path=str(csv_path),
            model=model,
            available_actions=twitter_actions,
        )

        env = oasis.make(
            agent_graph=agent_graph,
            platform=oasis.DefaultPlatformType.TWITTER,
            database_path=str(db_path),
        )
        await env.reset()

        # Seed: first agent posts the scenario trigger
        first = agent_graph.get_agent(0)
        if first is not None:
            actions = {first: ManualAction(action_type=ActionType.CREATE_POST, action_args={"content": "🚨 BREAKING: Major market announcement."})}
            await env.step(actions)

        for r in range(1, rounds + 1):
            actions = {
                agent: LLMAction()
                for _, agent in agent_graph.get_agents()
            }
            await env.step(actions)

            if sim_id:
                task_manager.emit_event(
                    sim_id, "round_complete",
                    {"track": 1, "round": r, "total_rounds": rounds},
                )

        await env.close()

        # Export SQLite → actions.jsonl with round field
        jsonl_path = tmpdir / "actions.jsonl"
        _export_db_to_jsonl(db_path, jsonl_path, rounds)

        return Track1Result(
            status="completed",
            actions_jsonl_path=str(jsonl_path),
            rounds=rounds,
        )
    except Exception:
        logger.exception("Track 1 OASIS simulation failed")
        return Track1Result(status="failed")
    finally:
        pass  # Keep tmpdir for inspection; caller handles cleanup


def _export_db_to_jsonl(db_path: Path, jsonl_path: Path, total_rounds: int) -> int:
    """Export OASIS SQLite post + trace tables to actions.jsonl with round field."""
    if not db_path.exists():
        return 0

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    count = 0

    with open(jsonl_path, "w") as f:
        cursor.execute("SELECT * FROM post ORDER BY created_at")
        for row in cursor.fetchall():
            action = {
                "agent_id": f"u_{row['user_id']:03d}",
                "action": "CREATE_POST",
                "content": row["content"],
                "post_id": row["post_id"],
                "round": total_rounds,
                "timestamp": row["created_at"],
                "num_likes": row["num_likes"],
                "num_shares": row["num_shares"],
            }
            f.write(json.dumps(action) + "\n")
            count += 1

        cursor.execute("SELECT * FROM trace ORDER BY created_at")
        for row in cursor.fetchall():
            action = {
                "agent_id": f"u_{row['user_id']:03d}",
                "action": row["action"],
                "content": row["info"],
                "round": total_rounds,
                "timestamp": row["created_at"],
            }
            f.write(json.dumps(action) + "\n")
            count += 1

    conn.close()
    return count
