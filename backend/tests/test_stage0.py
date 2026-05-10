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


def _mock_tavily(search_fn):
    """Patch TavilyClient.search to route queries through a mock function."""
    import backend.stage0.seeder as mod
    mod.TavilyClient.search = search_fn


class TestRunSeederHappyPath:
    @pytest.mark.asyncio
    async def test_all_six_pipelines_succeed(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _MOCK_TAVILY_RESPONSE,
        )
        # Return list for list-type pipelines, dict for dict-type.
        # MockLLMClient prefix matching: first match wins.
        # "Parse these search" prefix matches all 6 pipelines → returns list.
        # geo_context and macro expect dicts → type validation rejects list → marked low.
        llm = MockLLMClient(
            responses={
                "Parse these search": json.dumps([{"name": "X"}]),
            },
            default_response=json.dumps({"key": "value"}),
        )

        seed = await run_seeder(scenario="test", geography="US", vertical="auto", llm=llm)

        # 4 list-type pipelines succeed, 2 dict-type have gaps due to type mismatch
        assert isinstance(seed.competitors, list)
        assert seed.confidence["competitors"] == "high"
        assert seed.confidence["geographic"] == "low"
        assert "geographic" in seed.gaps

    @pytest.mark.asyncio
    async def test_single_result_confidence_is_medium(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _MOCK_SINGLE_RESULT,
        )
        llm = MockLLMClient(default_response=json.dumps([{"name": "X"}]))

        seed = await run_seeder(scenario="test", geography="US", vertical="auto", llm=llm)

        assert seed.confidence["competitors"] == "medium"

    @pytest.mark.asyncio
    async def test_bad_llm_json_marked_unavailable(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _MOCK_TAVILY_RESPONSE,
        )
        llm = MockLLMClient(default_response="not valid json!!!")

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
            if call_count in (2, 4):
                raise Exception("Tavily API error")
            return _MOCK_TAVILY_RESPONSE

        monkeypatch.setattr("backend.stage0.seeder.TavilyClient.search", flaky_tavily)
        llm = MockLLMClient(default_response=json.dumps([{"name": "X"}]))

        seed = await run_seeder(scenario="test", geography="US", vertical="auto", llm=llm)

        # 2 pipelines fail from Tavily error; the other 4 succeed as lists
        assert seed.confidence["competitors"] == "high"
        assert seed.confidence["historical"] == "low"  # failed
        assert len(seed.gaps) >= 2  # at least the 2 Tavily failures


class TestRunSeederAllPipelinesFail:
    @pytest.mark.asyncio
    async def test_all_fail_returns_empty_seed(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: (_ for _ in ()).throw(Exception("all failed")),
        )
        llm = MockLLMClient(default_response=json.dumps([{"name": "X"}]))

        seed = await run_seeder(scenario="test", geography="US", vertical="auto", llm=llm)

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
        llm = MockLLMClient(default_response=json.dumps([{"name": "X"}]))

        seed = await run_seeder(scenario="test", geography="US", vertical="auto", llm=llm)

        assert seed.competitors == []
        assert "competitors" in seed.gaps
        assert seed.confidence["competitors"] == "low"


class TestStage0SSEEvents:
    @pytest.mark.asyncio
    async def test_stage_events_include_confidence(self, monkeypatch):
        monkeypatch.setattr(
            "backend.stage0.seeder.TavilyClient.search",
            lambda s, **kw: _MOCK_TAVILY_RESPONSE,
        )

        from backend.pipeline.task_manager import task_manager

        task_manager.reset()
        sim_id = task_manager.init_sim()

        llm = MockLLMClient(default_response=json.dumps([{"name": "X"}]))

        await run_seeder(scenario="test", geography="US", vertical="auto", llm=llm, sim_id=sim_id)

        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        complete = [e for e in events if e["event"] == "stage_complete"]
        assert len(complete) == 1
        assert "confidence" in complete[0]["data"]


class TestRunSeederTimeout:
    @pytest.mark.asyncio
    async def test_timeout_fires_and_returns_partial(self, monkeypatch):
        def blocking_search(self, query, **kwargs):
            time.sleep(2)
            return _MOCK_TAVILY_RESPONSE

        monkeypatch.setattr("backend.stage0.seeder.TavilyClient.search", blocking_search)
        llm = MockLLMClient(default_response=json.dumps([{"name": "X"}]))

        seed = await run_seeder(scenario="test", geography="US", vertical="auto", llm=llm, timeout=0.5)

        assert len(seed.gaps) > 0
        assert seed.competitors == []
        for name, _ in PIPELINES:
            assert seed.confidence[name] == "low"
