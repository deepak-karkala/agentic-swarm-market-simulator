"""Stage 3: Parallel track orchestration.

Runs Tracks 1 (OASIS), 2 (Boardroom), and 3 (Analyst Desk) concurrently.
Track imports are lazy to avoid OASIS Twhin-BERT load at import time.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from backend.llm.client import LLMClient
from backend.pipeline.sim_stats import SimulationStats
from backend.stage0.seeder import RealitySeed

if TYPE_CHECKING:
    from backend.stage3.track1_oasis import Track1Result
    from backend.stage3.track2_boardroom import BoardroomResult
    from backend.stage3.track3_analyst import AnalystReport

logger = logging.getLogger(__name__)


@dataclass
class Stage3Result:
    track1: Track1Result | None = None  # noqa: F821
    track2: BoardroomResult | None = None  # noqa: F821
    track3: list[AnalystReport] = field(default_factory=list)  # noqa: F821
    stats: SimulationStats | None = None
    track2_failed: bool = False
    track3_failed: bool = False


async def run_stage3(
    seed: RealitySeed,
    twitter_profiles_csv: str,
    llm: LLMClient,
    rounds: int = 10,
    sim_id: str | None = None,
) -> Stage3Result:
    """Run all 3 simulation tracks in parallel.

    Any track may fail without crashing the others
    (asyncio.gather with return_exceptions=True).
    """
    from backend.pipeline.task_manager import task_manager
    from backend.stage3.track1_oasis import Track1Result, run_track1
    from backend.stage3.track2_boardroom import BoardroomResult, run_track2
    from backend.stage3.track3_analyst import generate_analyst_reports

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_start",
            {"stage": "stage3", "message": "Running 3-track simulation..."},
        )

    t1 = run_track1(twitter_profiles_csv, rounds=rounds, sim_id=sim_id)
    t2 = run_track2(seed, llm, sim_id=sim_id)
    t3 = generate_analyst_reports(seed, llm, sim_id=sim_id)

    r1, r2, r3 = await asyncio.gather(t1, t2, t3, return_exceptions=True)

    track1_result = r1 if isinstance(r1, Track1Result) else None
    track2_result = r2 if isinstance(r2, BoardroomResult) else None
    track3_result = r3 if isinstance(r3, list) else []

    t2_failed = isinstance(r2, Exception)
    t3_failed = isinstance(r3, Exception)

    if t2_failed:
        logger.warning("Track 2 failed: %s", r2)
    if t3_failed:
        logger.warning("Track 3 failed: %s", r3)

    stats = None
    if track1_result and track1_result.actions_jsonl_path:
        try:
            from pathlib import Path
            stats = SimulationStats.aggregate(Path(track1_result.actions_jsonl_path))
        except Exception:
            logger.exception("Failed to aggregate SimulationStats")

    if sim_id:
        task_manager.emit_event(
            sim_id, "stage_complete",
            {
                "stage": "stage3",
                "t1_status": track1_result.status if track1_result else "failed",
                "t2_status": track2_result.status if track2_result else "failed",
                "t2_failed": t2_failed,
                "t3_reports": len(track3_result),
                "t3_failed": t3_failed,
                "stats_available": stats is not None,
            },
        )

    return Stage3Result(
        track1=track1_result,
        track2=track2_result,
        track3=track3_result,
        stats=stats,
        track2_failed=t2_failed,
        track3_failed=t3_failed,
    )
