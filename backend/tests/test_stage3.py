"""Tests for Stage 3 Track 3: Analyst Desk."""

import json

import pytest

from backend.llm.mock_client import MockLLMClient
from backend.stage0.seeder import RealitySeed
from backend.stage3.track3_analyst import AnalystReport, generate_analyst_reports


_VALID_REPORT = json.dumps({
    "analyst_name": "Jane Smith",
    "firm": "Goldman Sachs",
    "target_company": "Tesla",
    "earnings_revision_pct": -5.0,
    "price_target_revision_pct": -10.0,
    "thesis_update": "Apple EV entry poses significant competitive risk.",
    "conviction": "high",
    "rating_change": "downgrade",
})

_INVALID_JSON = "not valid json {{{"


def _make_seed(**overrides) -> RealitySeed:
    seed = RealitySeed(geography="US", vertical="auto", scenario="Apple EV")
    seed.competitors = [{"name": "Tesla"}, {"name": "Ford"}]
    seed.kols = [{"name": "Elon Musk"}]
    seed.macro = {"rate": "5.5%", "regime": "neutral"}
    for k, v in overrides.items():
        setattr(seed, k, v)
    return seed


REQUIRED_KEYS = {
    "analyst_name", "firm", "target_company", "earnings_revision_pct",
    "price_target_revision_pct", "thesis_update", "conviction", "rating_change",
}


class TestAnalystReport:
    def test_schema_valid(self):
        data = json.loads(_VALID_REPORT)
        report = AnalystReport(**data)
        assert report.analyst_name == "Jane Smith"
        assert report.conviction == "high"
        assert report.earnings_revision_pct == -5.0

    def test_invalid_json_raises(self):
        with pytest.raises(Exception):
            AnalystReport(**json.loads(_INVALID_JSON))


class TestGenerateAnalystReports:
    @pytest.mark.asyncio
    async def test_produces_five_reports(self, monkeypatch):
        llm = MockLLMClient(default_response=_VALID_REPORT)
        seed = _make_seed()

        reports = await generate_analyst_reports(seed, llm, analyst_count=5)

        assert len(reports) == 5
        for r in reports:
            assert isinstance(r, AnalystReport)
            for key in REQUIRED_KEYS:
                assert getattr(r, key) is not None

    @pytest.mark.asyncio
    async def test_retry_on_invalid_json_then_succeeds(self, monkeypatch):
        call_count = 0

        async def retry_then_ok(prompt, tier, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _INVALID_JSON
            return _VALID_REPORT

        llm = MockLLMClient(default_response=_VALID_REPORT)
        monkeypatch.setattr(llm, "complete", retry_then_ok)

        seed = _make_seed()
        reports = await generate_analyst_reports(seed, llm, analyst_count=1)

        assert len(reports) == 1
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_double_failure_skips_analyst(self, monkeypatch):
        async def always_invalid(prompt, tier, **kwargs):
            return _INVALID_JSON

        llm = MockLLMClient(default_response=_VALID_REPORT)
        monkeypatch.setattr(llm, "complete", always_invalid)

        seed = _make_seed()
        reports = await generate_analyst_reports(seed, llm, analyst_count=3)

        assert len(reports) == 0  # all 3 skipped


class TestAnalystDeskSSE:
    @pytest.mark.asyncio
    async def test_track_events_emitted(self, monkeypatch):
        from backend.pipeline.task_manager import task_manager

        task_manager.reset()
        sim_id = task_manager.init_sim()

        llm = MockLLMClient(default_response=_VALID_REPORT)
        seed = _make_seed()

        await generate_analyst_reports(seed, llm, analyst_count=3, sim_id=sim_id)

        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        names = [e["event"] for e in events]
        assert "track_start" in names
        assert "track_complete" in names
        complete = [e for e in events if e["event"] == "track_complete"]
        assert complete[0]["data"]["track"] == 3
