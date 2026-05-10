"""Tests for Stage 3 Integration — parallel track orchestration."""

import pytest

from backend.llm.mock_client import MockLLMClient
from backend.stage0.seeder import RealitySeed
from backend.stage3.track1_oasis import Track1Result
from backend.stage3.track2_boardroom import BoardroomResult


def _make_seed() -> RealitySeed:
    seed = RealitySeed(geography="US", vertical="auto", scenario="Apple EV")
    seed.competitors = [{"name": "Tesla"}]
    seed.kols = [{"name": "Elon Musk"}]
    seed.macro = {"rate": "5.5%"}
    return seed


_SAMPLE_CSV = "user_id,name,username,user_char,description\n0,A,a,x,y\n"


class TestStage3Integration:
    @pytest.mark.asyncio
    async def test_all_three_tracks_launched_concurrently(self, monkeypatch):
        from backend.pipeline.sim_stats import SimulationStats

        calls = []

        async def mock_track1(csv, rounds, sim_id=None, timeout=1200):
            calls.append("track1")
            return Track1Result(status="completed", actions_jsonl_path="/fake/actions.jsonl", rounds=rounds)

        async def mock_track2(seed, llm, sim_id=None, timeout=1200):
            calls.append("track2")
            raise RuntimeError("Track 2 crash")

        async def mock_track3(seed, llm, analyst_count=10, sim_id=None):
            calls.append("track3")
            return []

        monkeypatch.setattr("backend.stage3.track1_oasis.run_track1", mock_track1)
        monkeypatch.setattr("backend.stage3.track2_boardroom.run_track2", mock_track2)
        monkeypatch.setattr("backend.stage3.track3_analyst.generate_analyst_reports", mock_track3)
        monkeypatch.setattr(SimulationStats, "aggregate", lambda path: SimulationStats(total_rounds=10))

        from backend.stage3 import run_stage3

        seed = _make_seed()
        llm = MockLLMClient()
        result = await run_stage3(seed, _SAMPLE_CSV, llm, rounds=5)

        assert len(calls) == 3
        assert result.track1.status == "completed"
        assert result.track2 is None
        assert result.track2_failed is True
        assert result.track3 is not None
        assert result.track3_failed is False
        assert result.stats.total_rounds == 10

    @pytest.mark.asyncio
    async def test_track3_crash_distinguished_from_zero_reports(self, monkeypatch):
        """Track 3 raising → track3_failed=True, track3 is empty list."""
        from backend.pipeline.sim_stats import SimulationStats

        async def mock_track1(csv, rounds, sim_id=None, timeout=1200):
            return Track1Result(status="completed", actions_jsonl_path="/fake/a.jsonl", rounds=3)

        async def mock_track2(seed, llm, sim_id=None, timeout=1200):
            return BoardroomResult(status="completed")

        async def mock_track3(seed, llm, analyst_count=10, sim_id=None):
            raise RuntimeError("Analyst desk crash")

        monkeypatch.setattr("backend.stage3.track1_oasis.run_track1", mock_track1)
        monkeypatch.setattr("backend.stage3.track2_boardroom.run_track2", mock_track2)
        monkeypatch.setattr("backend.stage3.track3_analyst.generate_analyst_reports", mock_track3)
        monkeypatch.setattr(SimulationStats, "aggregate", lambda path: SimulationStats())

        from backend.stage3 import run_stage3

        seed = _make_seed()
        llm = MockLLMClient()
        result = await run_stage3(seed, _SAMPLE_CSV, llm, rounds=3)

        assert result.track3_failed is True
        assert result.track3 == []
        assert result.track2_failed is False

    @pytest.mark.asyncio
    async def test_stats_unavailable_when_track1_no_path(self, monkeypatch):
        async def mock_track1(csv, rounds, sim_id=None, timeout=1200):
            return Track1Result(status="completed", actions_jsonl_path=None, rounds=rounds)

        async def mock_track2(seed, llm, sim_id=None, timeout=1200):
            return BoardroomResult(status="completed")

        async def mock_track3(seed, llm, analyst_count=10, sim_id=None):
            return []

        monkeypatch.setattr("backend.stage3.track1_oasis.run_track1", mock_track1)
        monkeypatch.setattr("backend.stage3.track2_boardroom.run_track2", mock_track2)
        monkeypatch.setattr("backend.stage3.track3_analyst.generate_analyst_reports", mock_track3)

        from backend.stage3 import run_stage3

        seed = _make_seed()
        llm = MockLLMClient()
        result = await run_stage3(seed, _SAMPLE_CSV, llm, rounds=3)

        assert result.stats is None

    @pytest.mark.asyncio
    async def test_sse_stage_events_emitted(self, monkeypatch):
        from backend.pipeline.task_manager import task_manager
        from backend.pipeline.sim_stats import SimulationStats

        task_manager.reset()
        sim_id = task_manager.init_sim()

        async def mock_track1(csv, rounds, sim_id=None, timeout=1200):
            return Track1Result(status="completed", actions_jsonl_path="/fake/a.jsonl", rounds=rounds)

        async def mock_track2(seed, llm, sim_id=None, timeout=1200):
            return BoardroomResult(status="completed")

        async def mock_track3(seed, llm, analyst_count=10, sim_id=None):
            raise RuntimeError("track 3 crash")

        monkeypatch.setattr("backend.stage3.track1_oasis.run_track1", mock_track1)
        monkeypatch.setattr("backend.stage3.track2_boardroom.run_track2", mock_track2)
        monkeypatch.setattr("backend.stage3.track3_analyst.generate_analyst_reports", mock_track3)
        monkeypatch.setattr(SimulationStats, "aggregate", lambda path: SimulationStats(total_rounds=5))

        from backend.stage3 import run_stage3

        seed = _make_seed()
        llm = MockLLMClient()
        await run_stage3(seed, _SAMPLE_CSV, llm, rounds=3, sim_id=sim_id)

        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        names = [e["event"] for e in events]
        assert "stage_start" in names
        complete = [e for e in events if e["event"] == "stage_complete"]
        assert len(complete) == 1
        data = complete[0]["data"]
        assert data["t3_failed"] is True
        assert data["t3_reports"] == 0
