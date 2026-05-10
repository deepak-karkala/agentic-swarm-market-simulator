"""Tests for Stage 1: Zep Graph Build."""

import pytest

from backend.llm.mock_client import MockLLMClient
from backend.stage0.seeder import RealitySeed
from backend.stage1.graph_builder import GraphResult, build_graph


def _make_seed(**overrides) -> RealitySeed:
    seed = RealitySeed(geography="US", vertical="auto", scenario="Apple EV")
    seed.competitors = [{"name": "Tesla", "market_share": "60%"}]
    seed.historical_precedents = [{"scenario": "iPhone launch", "outcome": "disrupted"}]
    seed.geo_context = {"price_sensitivity": "medium"}
    seed.regulatory = [{"policy": "EV tax credit"}]
    seed.kols = [{"name": "Elon Musk"}]
    seed.macro = {"rate": "5.5%"}
    for k, v in overrides.items():
        setattr(seed, k, v)
    return seed


class TestGraphResult:
    def test_default_is_fallback(self):
        result = GraphResult()
        assert result.fallback_mode is True
        assert result.graph_id is None
        assert result.node_count == 0

    def test_success_result(self):
        result = GraphResult(graph_id="g_123", node_count=47, fallback_mode=False, ontology_set=True)
        assert result.graph_id == "g_123"
        assert result.node_count == 47
        assert result.fallback_mode is False


class TestBuildGraphFallback:
    @pytest.mark.asyncio
    async def test_fallback_when_no_zep_key(self, monkeypatch):
        monkeypatch.delenv("ZEP_API_KEY", raising=False)

        seed = _make_seed()
        llm = MockLLMClient()
        result = await build_graph(seed, llm)

        assert isinstance(result, GraphResult)
        assert result.fallback_mode is True
        assert result.graph_id is None
        assert result.raw_context is not None

    @pytest.mark.asyncio
    async def test_fallback_contains_stage0_data(self, monkeypatch):
        monkeypatch.delenv("ZEP_API_KEY", raising=False)

        seed = _make_seed()
        llm = MockLLMClient()
        result = await build_graph(seed, llm)

        ctx = result.raw_context
        assert ctx is not None
        assert ctx["scenario"] == "Apple EV"
        assert ctx["geography"] == "US"
        assert isinstance(ctx["competitors"], list)


class TestBuildGraphSSE:
    @pytest.mark.asyncio
    async def test_stage_events_emitted_on_fallback(self, monkeypatch):
        monkeypatch.delenv("ZEP_API_KEY", raising=False)

        from backend.pipeline.task_manager import task_manager

        task_manager.reset()
        sim_id = task_manager.init_sim()

        seed = _make_seed()
        llm = MockLLMClient()
        await build_graph(seed, llm, sim_id=sim_id)

        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        event_names = [e["event"] for e in events]
        assert "stage_start" in event_names
        assert "stage_complete" in event_names
