"""Tests for Stage 2: Agent Factory."""

import csv
import io
import json

import pytest

from backend.llm.client import ModelTier
from backend.llm.mock_client import MockLLMClient
from backend.stage1.graph_builder import GraphResult
from backend.stage2.agent_factory import AgentFactoryError, AgentProfile, generate_agents


_SAMPLE_PROFILE_JSON = json.dumps({
    "name": "Alex Chen",
    "username": "alexchen_tech",
    "user_char": "Tech enthusiast and early adopter. Loves EVs.",
    "description": "Tech enthusiast | EV lover",
})

_EMPTY_GRAPH = GraphResult(
    raw_context={
        "scenario": "Apple EV at $35K",
        "geography": "US",
        "vertical": "auto",
        "competitors": [{"name": "Tesla", "market_share": "60%"}],
        "kols": [{"name": "Elon Musk", "platform": "Twitter"}],
        "macro": {"rate": "5.5%", "regime": "neutral"},
    },
)

_NO_COMPETITORS_GRAPH = GraphResult(
    raw_context={
        "scenario": "Apple EV at $35K",
        "geography": "US",
        "vertical": "auto",
        "competitors": [],
        "kols": [],
        "macro": {},
    },
)

REDDIT_REQUIRED_KEYS = {"user_id", "username", "name", "bio", "persona", "karma",
                        "age", "gender", "mbti", "country"}


def _parse_csv(csv_str: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(csv_str)))


class TestAgentProfile:
    def test_creates_from_dict(self):
        p = AgentProfile(user_id="u_001", name="A", username="a", user_char="x", description="y")
        assert p.user_id == "u_001"
        assert p.name == "A"

    def test_csv_row_columns(self):
        p = AgentProfile(user_id="u_001", name="A", username="a", user_char="x", description="y")
        assert set(p.to_csv_row()) == {"user_id", "name", "username", "user_char", "description"}


class TestGenerateAgents:
    @pytest.mark.asyncio
    async def test_produces_consumer_profiles(self, monkeypatch):
        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)
        result = await generate_agents(_EMPTY_GRAPH, llm, consumer_count=10, csuite_count=0, analyst_count=0)
        rows = _parse_csv(result.twitter_profiles_csv)
        assert len(rows) == 10
        for r in rows:
            assert set(r) == {"user_id", "name", "username", "user_char", "description"}

    @pytest.mark.asyncio
    async def test_model_tier_routing(self, monkeypatch):
        """Consumer→HAIKU, C-suite/analyst→SONNET."""
        tiers_called = []

        async def record_tier(prompt, tier, **kwargs):
            tiers_called.append(tier)
            return _SAMPLE_PROFILE_JSON

        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)
        monkeypatch.setattr(llm, "complete", record_tier)

        await generate_agents(
            _EMPTY_GRAPH, llm,
            consumer_count=3, csuite_count=3, analyst_count=2,
        )

        # First 3 are consumers (HAIKU), rest are csuite+analyst (SONNET)
        assert tiers_called[:3] == [ModelTier.HAIKU] * 3
        assert all(t == ModelTier.SONNET for t in tiers_called[3:])

    @pytest.mark.asyncio
    async def test_individual_failure_is_skipped(self, monkeypatch):
        called = 0

        async def flaky(prompt, tier, **kwargs):
            nonlocal called
            called += 1
            if called in (3, 7, 12):
                from backend.llm.client import LLMRateLimitError
                raise LLMRateLimitError("rate limited")
            return _SAMPLE_PROFILE_JSON

        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)
        monkeypatch.setattr(llm, "complete", flaky)

        result = await generate_agents(_EMPTY_GRAPH, llm, consumer_count=15, csuite_count=0, analyst_count=0)
        rows = _parse_csv(result.twitter_profiles_csv)
        assert len(rows) == 12  # 3 failures

    @pytest.mark.asyncio
    async def test_below_eighty_percent_raises(self, monkeypatch):
        async def mostly_fails(prompt, tier, **kwargs):
            if hash(prompt) % 3 != 0:
                from backend.llm.client import LLMRateLimitError
                raise LLMRateLimitError("rate limited")
            return _SAMPLE_PROFILE_JSON

        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)
        monkeypatch.setattr(llm, "complete", mostly_fails)

        with pytest.raises(AgentFactoryError, match="80%"):
            await generate_agents(_EMPTY_GRAPH, llm, consumer_count=15, csuite_count=0, analyst_count=0)

    @pytest.mark.asyncio
    async def test_csuite_count_respects_available_competitors(self, monkeypatch):
        """With 0 competitors, csuite_count of 50 generates 0 csuite tasks.
        Threshold is based on scheduled count, so only consumers + analysts count."""
        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)

        result = await generate_agents(
            _NO_COMPETITORS_GRAPH, llm,
            consumer_count=10, csuite_count=50, analyst_count=3,
        )

        rows = _parse_csv(result.twitter_profiles_csv)
        # 10 consumers + 3 analysts = 13 total (no csuite because no competitors)
        assert len(rows) == 13

    @pytest.mark.asyncio
    async def test_reddit_json_has_full_schema(self, monkeypatch):
        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)
        result = await generate_agents(_EMPTY_GRAPH, llm, consumer_count=3, csuite_count=0, analyst_count=0)
        reddit = json.loads(result.reddit_profiles_json)
        assert len(reddit) == 3
        for item in reddit:
            assert set(item.keys()) == REDDIT_REQUIRED_KEYS, f"Missing/extra keys: {set(item.keys()) ^ REDDIT_REQUIRED_KEYS}"
            assert item["user_id"].startswith("u_")
            assert isinstance(item["karma"], int)


class TestGenerateAgentsSSE:
    @pytest.mark.asyncio
    async def test_stage_events_emitted(self, monkeypatch):
        from backend.pipeline.task_manager import task_manager

        task_manager.reset()
        sim_id = task_manager.init_sim()

        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)
        await generate_agents(_EMPTY_GRAPH, llm, consumer_count=5, csuite_count=0, analyst_count=0, sim_id=sim_id)

        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        names = [e["event"] for e in events]
        assert "stage_start" in names
        assert "stage_complete" in names
        complete = [e for e in events if e["event"] == "stage_complete"]
        assert complete[0]["data"]["agent_count"] == 5
