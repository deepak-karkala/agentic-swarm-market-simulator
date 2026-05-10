"""Tests for Stage 1: Zep Graph Build."""

import pytest

from backend.llm.mock_client import MockLLMClient
from backend.stage0.seeder import RealitySeed
from backend.stage1.graph_builder import GraphResult, build_graph, _format_context_for_zep


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
        assert result.estimated_node_count == 0


class TestBuildGraphFallback:
    @pytest.mark.asyncio
    async def test_fallback_when_no_zep_key(self, monkeypatch):
        monkeypatch.delenv("ZEP_API_KEY", raising=False)

        seed = _make_seed()
        llm = MockLLMClient()
        result = await build_graph(seed, llm)

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


class TestBuildGraphZepSuccess:
    @pytest.mark.asyncio
    async def test_zep_called_with_correct_graph_name(self, monkeypatch):
        monkeypatch.setenv("ZEP_API_KEY", "zep-fake-key")

        calls = {}

        class MockGraph:
            @staticmethod
            def create(graph_id, name=None, description=None):
                calls["create"] = {"graph_id": graph_id, "description": description}
                return graph_id

            @staticmethod
            def add_data(graph_id, data):
                calls["add_data"] = {"graph_id": graph_id, "data_len": len(data)}

        class MockZep:
            def __init__(self, api_key):
                self.graph = MockGraph()

        monkeypatch.setattr(
            "backend.stage1.graph_builder.Zep",
            MockZep,
        )

        seed = _make_seed()
        llm = MockLLMClient()
        result = await build_graph(seed, llm)

        assert result.fallback_mode is False
        assert result.graph_id == "sim-US-auto"
        assert result.estimated_node_count > 0
        assert calls["create"]["graph_id"] == "sim-US-auto"
        assert "Apple EV" in calls["create"]["description"]
        assert calls["add_data"]["graph_id"] == "sim-US-auto"
        assert calls["add_data"]["data_len"] > 100

    @pytest.mark.asyncio
    async def test_zep_failure_falls_back_with_context(self, monkeypatch):
        monkeypatch.setenv("ZEP_API_KEY", "zep-fake-key")

        class FailingZep:
            def __init__(self, api_key):
                raise Exception("Zep API down")

        monkeypatch.setattr(
            "backend.stage1.graph_builder.Zep",
            FailingZep,
        )

        seed = _make_seed()
        llm = MockLLMClient()
        result = await build_graph(seed, llm)

        assert result.fallback_mode is True
        assert result.graph_id is None
        assert result.raw_context is not None
        assert result.raw_context["competitors"][0]["name"] == "Tesla"


class TestFormatContext:
    def test_includes_all_sections(self):
        seed = _make_seed()
        from backend.stage1.graph_builder import _seed_to_context
        ctx = _seed_to_context(seed)
        text = _format_context_for_zep(ctx)

        assert "Apple EV" in text
        assert "Competitors" in text
        assert "Geographic Context" in text
        assert "Regulatory Environment" in text


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

    @pytest.mark.asyncio
    async def test_stage_events_emitted_on_success(self, monkeypatch):
        monkeypatch.setenv("ZEP_API_KEY", "zep-fake-key")

        class MockGraph:
            @staticmethod
            def create(graph_id, name=None, description=None):
                return graph_id

            @staticmethod
            def add_data(graph_id, data):
                pass

        class MockZep:
            def __init__(self, api_key):
                self.graph = MockGraph()

        monkeypatch.setattr(
            "backend.stage1.graph_builder.Zep",
            MockZep,
        )

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

        complete = [e for e in events if e["event"] == "stage_complete"]
        assert len(complete) == 1
        assert complete[0]["data"]["graph_id"] == "sim-US-auto"
