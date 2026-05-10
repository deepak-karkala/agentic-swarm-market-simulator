"""Stage 3 Track 1: OASIS Twitter Social Simulation.

Runs OASIS in-process (not subprocess), tracking rounds externally
and exporting SQLite output to actions.jsonl with per-record round field.

Architecture note: Track 1 constructs its own Camel model from environment
variables rather than using the shared LLMClient abstraction because OASIS
requires a Camel BaseModelBackend instance (not a plain completion string).
This is a known exception — all other stages use LLMClient directly.

Source: https://docs.oasis.camel-ai.org — OASIS runs via env.step() loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class Track1Result:
    status: str = "failed"  # completed | failed | timeout
    actions_jsonl_path: str | None = None
    rounds: int = 0
    agent_count: int = 0


async def run_track1(
    twitter_profiles_csv: str,
    rounds: int = 10,
    sim_id: str | None = None,
    timeout: float = 1200.0,
) -> Track1Result:
    """Run OASIS Twitter simulation with per-round JSONL export.

    agent_count is derived from the CSV row count.
    Round field is written per-record during each env.step() — not
    fabricated at export time.
    """
    from backend.pipeline.task_manager import task_manager

    agent_count = _csv_row_count(twitter_profiles_csv)

    if sim_id:
        task_manager.emit_event(
            sim_id, "track_start",
            {"track": 1, "message": "Running public narrative simulation...", "agents": agent_count},
        )

    try:
        result = await asyncio.wait_for(
            _run_oasis_simulation(twitter_profiles_csv, rounds, sim_id),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Track 1 timed out after %.1fs", timeout)
        result = Track1Result(status="timeout", agent_count=agent_count)
        if sim_id:
            task_manager.emit_event(sim_id, "track_complete", {"track": 1, "status": "timeout"})
        return result

    result.agent_count = agent_count

    if sim_id:
        task_manager.emit_event(
            sim_id, "track_complete",
            {"track": 1, "status": result.status, "rounds": result.rounds, "agents": agent_count},
        )

    return result


async def _run_oasis_simulation(
    profiles_csv: str,
    rounds: int,
    sim_id: str | None,
) -> Track1Result:
    from backend.pipeline.task_manager import task_manager

    # Lazy imports — OASIS loads Twhin-BERT which is slow
    from camel.configs import AnthropicConfig
    from camel.models import ModelFactory
    from camel.types import ModelPlatformType, ModelType
    from oasis import ActionType, LLMAction, ManualAction, generate_twitter_agent_graph
    import oasis

    twitter_actions = ActionType.get_default_twitter_actions()

    api_key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("No API key available for OASIS simulation")

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

        # Seed round (round 0): first agent posts the trigger
        first = agent_graph.get_agent(0)
        if first is not None:
            actions = {first: ManualAction(action_type=ActionType.CREATE_POST, action_args={"content": "🚨 BREAKING: Major market announcement."})}
            await env.step(actions)
        _append_posts_jsonl(db_path, tmpdir / "actions.jsonl", round_num=0)

        for r in range(1, rounds + 1):
            actions = {agent: LLMAction() for _, agent in agent_graph.get_agents()}
            await env.step(actions)
            _append_posts_jsonl(db_path, tmpdir / "actions.jsonl", round_num=r)

            if sim_id:
                task_manager.emit_event(
                    sim_id, "round_complete",
                    {"track": 1, "round": r, "total_rounds": rounds},
                )

        await env.close()

        return Track1Result(
            status="completed",
            actions_jsonl_path=str(tmpdir / "actions.jsonl"),
            rounds=rounds,
        )
    except Exception:
        logger.exception("Track 1 OASIS simulation failed")
        return Track1Result(status="failed")
    # tmpdir intentionally not cleaned up — caller owns the artifacts


def _append_posts_jsonl(db_path: Path, jsonl_path: Path, round_num: int) -> int:
    """Append new post records from SQLite to JSONL with the current round."""
    if not db_path.exists():
        return 0

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    count = 0

    with open(jsonl_path, "a") as f:
        cursor.execute("SELECT * FROM post ORDER BY created_at")
        for row in cursor.fetchall():
            # Skip posts already written (idempotent — post_id is unique)
            action = {
                "agent_id": f"u_{row['user_id']:03d}",
                "action": "CREATE_POST",
                "content": row["content"],
                "post_id": row["post_id"],
                "round": round_num,
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
                "round": round_num,
                "timestamp": row["created_at"],
            }
            f.write(json.dumps(action) + "\n")
            count += 1

    conn.close()
    return count


def _csv_row_count(csv_text: str) -> int:
    """Count data rows in CSV (excluding header)."""
    lines = [line for line in csv_text.strip().split("\n") if line.strip()]
    return max(0, len(lines) - 1)
