"""Tests for Stage 3.5: Expert Panel."""

import json

import pytest

from backend.llm.mock_client import MockLLMClient
from backend.pipeline.sim_stats import SimulationStats
from backend.stage0.seeder import RealitySeed
from backend.stage35.expert_panel import ExpertAnalysis, run_expert_panel


_FAKE_ANALYSIS = json.dumps({
    "summary": "The competitive landscape is shifting.",
    "key_findings": ["Finding 1", "Finding 2"],
    "confidence": "high",
    "caveats": ["Based on limited data"],
})

_MISSING_KEY_ANALYSIS = json.dumps({
    "summary": "Some text.",
    "confidence": "medium",
    # key_findings and caveats missing
})

_BAD_CONFIDENCE_ANALYSIS = json.dumps({
    "summary": "Text.",
    "key_findings": ["F1"],
    "confidence": "impossible",
    "caveats": [],
})

_NON_LIST_FINDINGS = json.dumps({
    "summary": "Text.",
    "key_findings": "not a list",
    "confidence": "medium",
    "caveats": [],
})


def _make_seed() -> RealitySeed:
    seed = RealitySeed(geography="US", vertical="auto", scenario="Apple EV")
    seed.competitors = [{"name": "Tesla"}]
    seed.kols = [{"name": "Elon Musk"}]
    seed.macro = {"rate": "5.5%"}
    seed.confidence = {k: "high" for k in ("competitors", "historical", "geographic", "regulatory", "kols", "macro")}
    return seed


def _make_stats() -> SimulationStats:
    return SimulationStats(
        total_rounds=10,
        per_round_sentiment=[
            {"round": 1, "positive_pct": 60, "negative_pct": 20, "neutral_pct": 20},
        ],
        adoption_proxy={"early_adopters_pct": 40, "mainstream_pct": 35, "laggards_pct": 25},
        agent_group_summary={"consumer": 200},
    )


class TestExpertAnalysis:
    def test_default_is_placeholder(self):
        a = ExpertAnalysis()
        assert "unavailable" in a.summary
        assert a.confidence == "low"

    def test_with_data(self):
        a = ExpertAnalysis(
            summary="Market is growing.",
            key_findings=["Growth expected"],
            confidence="high",
            caveats=["Limited sample"],
        )
        assert a.confidence == "high"
        assert len(a.key_findings) == 1


class TestRunExpertPanel:
    @pytest.mark.asyncio
    async def test_all_five_experts_run(self, monkeypatch):
        llm = MockLLMClient(default_response=_FAKE_ANALYSIS)
        seed = _make_seed()
        stats = _make_stats()

        result = await run_expert_panel(seed, stats, llm)

        assert "competitive" in result
        assert "economic" in result
        assert "consumer" in result
        assert "domain" in result
        assert "regulatory" in result
        assert result["competitive"].confidence == "high"

    @pytest.mark.asyncio
    async def test_agent_timeout_produces_placeholder(self, monkeypatch):
        import asyncio

        async def slow(prompt, tier, **kwargs):
            await asyncio.sleep(99)
            return _FAKE_ANALYSIS

        llm = MockLLMClient(default_response=_FAKE_ANALYSIS)
        monkeypatch.setattr(llm, "complete", slow)

        seed = _make_seed()
        stats = _make_stats()

        result = await run_expert_panel(seed, stats, llm, per_agent_timeout=0.1)

        assert result["competitive"].confidence == "low"
        assert "unavailable" in result["competitive"].summary

    @pytest.mark.asyncio
    async def test_sse_events_emitted(self, monkeypatch):
        from backend.pipeline.task_manager import task_manager

        task_manager.reset()
        sim_id = task_manager.init_sim()

        llm = MockLLMClient(default_response=_FAKE_ANALYSIS)
        seed = _make_seed()
        stats = _make_stats()

        await run_expert_panel(seed, stats, llm, sim_id=sim_id)

        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        names = [e["event"] for e in events]
        assert "stage_start" in names
        assert "stage_complete" in names

    @pytest.mark.asyncio
    async def test_missing_keys_produces_placeholder(self, monkeypatch):
        llm = MockLLMClient(default_response=_MISSING_KEY_ANALYSIS)
        seed = _make_seed()
        stats = _make_stats()

        result = await run_expert_panel(seed, stats, llm)
        assert result["competitive"].confidence == "low"
        assert "unavailable" in result["competitive"].summary

    @pytest.mark.asyncio
    async def test_bad_confidence_produces_placeholder(self, monkeypatch):
        llm = MockLLMClient(default_response=_BAD_CONFIDENCE_ANALYSIS)
        seed = _make_seed()
        stats = _make_stats()

        result = await run_expert_panel(seed, stats, llm)
        assert result["competitive"].confidence == "low"

    @pytest.mark.asyncio
    async def test_non_list_key_findings_produces_placeholder(self, monkeypatch):
        llm = MockLLMClient(default_response=_NON_LIST_FINDINGS)
        seed = _make_seed()
        stats = _make_stats()

        result = await run_expert_panel(seed, stats, llm)
        assert result["competitive"].confidence == "low"
