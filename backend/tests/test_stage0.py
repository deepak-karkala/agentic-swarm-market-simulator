"""Tests for Stage 0: Reality Seeding."""

import json
import time

import pytest

from backend.llm.mock_client import MockLLMClient
from backend.stage0.seeder import PIPELINES, run_seeder


_MOCK_TAVILY_RESPONSE = {
    "results": [
        {"title": "A", "url": "https://x.com/a", "content": "..."},
        {"title": "B", "url": "https://x.com/b", "content": "..."},
    ]
}
_MOCK_SINGLE_RESULT = {
    "results": [{"title": "A", "url": "https://x.com/a", "content": "..."}]
}
_EMPTY_TAVILY_RESPONSE = {"results": []}


@pytest.fixture(autouse=True)
def _set_fake_tavily_key(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-fake-key")


def _make_llm(monkeypatch, responses: dict[str, str]) -> MockLLMClient:
    """Create a MockLLMClient with per-pipeline routed responses.
    Pipeline name is matched against the prompt text."""
    llm = MockLLMClient()

    async def _route(prompt, tier, **kwargs):
        for name, response in responses.items():
            if name in prompt:
                return response
        return responses.get("*", '""')

    monkeypatch.setattr(llm, "complete", _route)
    return llm


class TestRunSeederHappyPath:
    @pytest.mark.asyncio
    async def test_all_six_pipelines_succeed_mixed_types(self, monkeypatch):
        """True happy path: list pipelines receive lists, dict pipelines receive dicts."""
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _MOCK_TAVILY_RESPONSE,
        )
        llm = _make_llm(monkeypatch, {
            "competitors": json.dumps([{"name": "Apple", "share": "0%"}]),
            "historical": json.dumps([{"scenario": "iPhone launch", "outcome": "market disruption"}]),
            "geographic": json.dumps({"price_sensitivity": "medium", "adoption_curve": "growth"}),
            "regulatory": json.dumps([{"policy": "EV tax credit", "type": "subsidy"}]),
            "kols": json.dumps([{"name": "Elon Musk", "platform": "Twitter"}]),
            "macro": json.dumps({"rate": "5.5%", "regime": "neutral"}),
        })

        seed = await run_seeder(scenario="test", geography="US", vertical="auto", llm=llm)

        assert len(seed.gaps) == 0
        assert isinstance(seed.competitors, list)
        assert len(seed.competitors) == 1
        assert seed.competitors[0]["name"] == "Apple"
        assert isinstance(seed.geo_context, dict)
        assert seed.geo_context["price_sensitivity"] == "medium"
        assert isinstance(seed.macro, dict)
        assert seed.macro["rate"] == "5.5%"
        assert seed.confidence["competitors"] == "high"
        assert seed.confidence["geographic"] == "high"
        assert seed.confidence["macro"] == "high"

    @pytest.mark.asyncio
    async def test_single_result_confidence_is_medium(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _MOCK_SINGLE_RESULT,
        )
        llm = _make_llm(monkeypatch, {"*": json.dumps([{"name": "X"}])})

        seed = await run_seeder(scenario="test", geography="US", vertical="auto", llm=llm)

        assert seed.confidence["competitors"] == "medium"

    @pytest.mark.asyncio
    async def test_bad_llm_json_marked_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _MOCK_TAVILY_RESPONSE,
        )
        llm = _make_llm(monkeypatch, {"*": "not valid json!!!"})

        seed = await run_seeder(scenario="test", geography="US", vertical="auto", llm=llm)

        assert seed.competitors == []
        assert "competitors" in seed.gaps
        assert seed.confidence["competitors"] == "low"


class TestRunSeederPartialFailure:
    @pytest.mark.asyncio
    async def test_failed_pipelines_flagged_in_gaps(self, monkeypatch):
        call_count = 0

        def flaky_tavily(self, query, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count in (2, 4):  # historical=2nd, regulatory=4th
                raise Exception("Tavily API error")
            return _MOCK_TAVILY_RESPONSE

        monkeypatch.setattr("backend.stage0.seeder.TavilyClient.search", flaky_tavily)
        llm = _make_llm(monkeypatch, {"*": json.dumps([{"name": "X"}])})

        seed = await run_seeder(scenario="test", geography="US", vertical="auto", llm=llm)

        # Pipelines 2 (historical) and 4 (regulatory) failed via Tavily error
        assert seed.confidence["competitors"] == "high"
        assert seed.confidence["historical"] == "low"
        assert seed.confidence["regulatory"] == "low"
        assert "historical" in seed.gaps
        assert "regulatory" in seed.gaps


class TestRunSeederAllPipelinesFail:
    @pytest.mark.asyncio
    async def test_all_fail_returns_empty_seed(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: (_ for _ in ()).throw(Exception("all failed")),
        )

        seed = await run_seeder(scenario="test", geography="US", vertical="auto",
                                llm=MockLLMClient())

        assert seed.is_empty is True
        for name, _ in PIPELINES:
            assert seed.confidence[name] == "low"


class TestRunSeederEmptyResults:
    @pytest.mark.asyncio
    async def test_empty_tavily_response_marks_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _EMPTY_TAVILY_RESPONSE,
        )

        seed = await run_seeder(scenario="test", geography="US", vertical="auto",
                                llm=MockLLMClient())

        assert seed.competitors == []
        assert "competitors" in seed.gaps
        assert seed.confidence["competitors"] == "low"


class TestStage0SSEEvents:
    @pytest.mark.asyncio
    async def test_stage_events_include_confidence_with_values(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _MOCK_TAVILY_RESPONSE,
        )
        llm = _make_llm(monkeypatch, {"*": json.dumps([{"name": "X"}])})

        from backend.pipeline.task_manager import task_manager

        task_manager.reset()
        sim_id = task_manager.init_sim()

        await run_seeder(scenario="test", geography="US", vertical="auto",
                         llm=llm, sim_id=sim_id)

        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        complete = [e for e in events if e["event"] == "stage_complete"]
        assert len(complete) == 1
        data = complete[0]["data"]
        assert data["confidence"]["competitors"] == "high"
        assert isinstance(data["confidence"]["kols"], str)


class TestRunSeederTimeout:
    @pytest.mark.asyncio
    async def test_timeout_fires_and_returns_partial(self, monkeypatch):
        def blocking_search(self, query, **kwargs):
            time.sleep(2)
            return _MOCK_TAVILY_RESPONSE

        monkeypatch.setattr("backend.stage0.seeder.TavilyClient.search", blocking_search)

        seed = await run_seeder(scenario="test", geography="US", vertical="auto",
                                llm=MockLLMClient(), timeout=0.5)

        assert len(seed.gaps) > 0
        assert seed.competitors == []
        for name, _ in PIPELINES:
            assert seed.confidence[name] == "low"
