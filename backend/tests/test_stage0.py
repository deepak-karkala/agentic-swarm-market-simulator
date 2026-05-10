"""Tests for Stage 0: Reality Seeding."""

import pytest

from backend.llm.mock_client import MockLLMClient
from backend.stage0.seeder import PIPELINES, RealitySeed, run_seeder


_FAKE_RESULT = '{"name": "TestCo", "summary": "test data"}'
_MOCK_TAVILY_RESPONSE = {
    "results": [
        {
            "title": "Apple EV Launch",
            "url": "https://example.com/apple-ev",
            "content": "Apple plans to launch an electric vehicle at $35,000...",
        },
        {
            "title": "EV Market Analysis",
            "url": "https://example.com/ev-market",
            "content": "The EV market is growing rapidly...",
        },
    ]
}

_EMPTY_TAVILY_RESPONSE = {"results": []}


@pytest.fixture(autouse=True)
def _set_fake_tavily_key(monkeypatch):
    """Set a fake TAVILY_API_KEY so TavilyClient() constructor doesn't fail."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-fake-key")


class TestRunSeederHappyPath:
    @pytest.mark.asyncio
    async def test_all_six_pipelines_succeed(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _MOCK_TAVILY_RESPONSE,
        )

        llm = MockLLMClient(default_response=_FAKE_RESULT)

        seed = await run_seeder(
            scenario="Apple EV at $35K",
            geography="US",
            vertical="auto",
            llm=llm,
        )

        assert isinstance(seed, RealitySeed)
        assert len(seed.gaps) == 0

    @pytest.mark.asyncio
    async def test_output_fields_mapped_correctly(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _MOCK_TAVILY_RESPONSE,
        )

        llm = MockLLMClient(default_response=_FAKE_RESULT)

        seed = await run_seeder(
            scenario="Apple EV at $35K",
            geography="India",
            vertical="pharma",
            llm=llm,
        )

        assert seed.geography == "India"
        assert seed.vertical == "pharma"
        assert seed.competitors != "unavailable"
        assert seed.historical_precedents != "unavailable"
        assert seed.geo_context != "unavailable"
        assert seed.regulatory != "unavailable"
        assert seed.kols != "unavailable"
        assert seed.macro != "unavailable"
        assert isinstance(seed.gaps, list)


class TestRunSeederPartialFailure:
    @pytest.mark.asyncio
    async def test_failed_pipelines_flagged_in_gaps(self, monkeypatch):
        call_count = 0

        def flaky_tavily(self, query, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count in (2, 4):
                raise Exception("Tavily API error")
            return _MOCK_TAVILY_RESPONSE

        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            flaky_tavily,
        )

        llm = MockLLMClient(default_response=_FAKE_RESULT)

        seed = await run_seeder(
            scenario="Apple EV at $35K",
            geography="US",
            vertical="auto",
            llm=llm,
        )

        assert len(seed.gaps) == 2


class TestRunSeederAllPipelinesFail:
    @pytest.mark.asyncio
    async def test_all_fail_returns_empty_seed(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: (_ for _ in ()).throw(Exception("all failed")),
        )

        llm = MockLLMClient(default_response=_FAKE_RESULT)

        seed = await run_seeder(
            scenario="Apple EV at $35K",
            geography="US",
            vertical="auto",
            llm=llm,
        )

        assert len(seed.gaps) >= len(PIPELINES)
        assert seed.is_empty is True
        assert seed.competitors == "unavailable"


class TestRunSeederEmptyResults:
    @pytest.mark.asyncio
    async def test_empty_tavily_response_marks_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _EMPTY_TAVILY_RESPONSE,
        )

        llm = MockLLMClient(default_response=_FAKE_RESULT)

        seed = await run_seeder(
            scenario="Apple EV at $35K",
            geography="US",
            vertical="auto",
            llm=llm,
        )

        assert seed.competitors == "unavailable"
        assert "competitors" in seed.gaps


class TestStage0SSEEvents:
    @pytest.mark.asyncio
    async def test_stage_start_and_complete_events_emitted(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _MOCK_TAVILY_RESPONSE,
        )

        from backend.pipeline.task_manager import task_manager

        task_manager.reset()
        sim_id = task_manager.init_sim()

        llm = MockLLMClient(default_response=_FAKE_RESULT)

        await run_seeder(
            scenario="Apple EV at $35K",
            geography="US",
            vertical="auto",
            llm=llm,
            sim_id=sim_id,
        )

        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        assert len(events) >= 2
        event_names = [e["event"] for e in events]
        assert "stage_complete" in event_names


class TestRunSeederTimeout:
    @pytest.mark.asyncio
    async def test_timeout_fires_and_returns_partial(self, monkeypatch):
        import asyncio

        async def slow_search(self, query, **kwargs):
            await asyncio.sleep(999)
            return _MOCK_TAVILY_RESPONSE

        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            slow_search,
        )

        llm = MockLLMClient(default_response=_FAKE_RESULT)

        seed = await run_seeder(
            scenario="Apple EV at $35K",
            geography="US",
            vertical="auto",
            llm=llm,
            timeout=0.5,
        )

        assert len(seed.gaps) > 0
        assert seed.competitors == "unavailable"

