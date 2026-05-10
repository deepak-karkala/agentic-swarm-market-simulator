"""Tests for Stage 2: Agent Factory."""

import csv
import io
import json

import pytest

from backend.llm.mock_client import MockLLMClient
from backend.stage1.graph_builder import GraphResult
from backend.stage2.agent_factory import (
    AgentProfile,
    AgentFactoryError,
    generate_agents,
)


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


def _parse_csv(csv_str: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_str))
    return list(reader)


class TestAgentProfile:
    def test_creates_from_dict(self):
        profile = AgentProfile(
            user_id="u_001",
            name="Alex Chen",
            username="alexchen_tech",
            user_char="Early adopter.",
            description="Tech enthusiast",
        )
        assert profile.user_id == "u_001"
        assert profile.name == "Alex Chen"

    def test_csv_columns_match_required_spec(self):
        profile = AgentProfile(
            user_id="u_001",
            name="Alex",
            username="alex",
            user_char="...",
            description="...",
        )
        row = profile.to_csv_row()
        assert set(row.keys()) == {"user_id", "name", "username", "user_char", "description"}


class TestGenerateAgents:
    @pytest.mark.asyncio
    async def test_produces_consumer_profiles(self, monkeypatch):
        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)

        result = await generate_agents(
            graph=_EMPTY_GRAPH,
            llm=llm,
            consumer_count=10,
            csuite_count=0,
            analyst_count=0,
        )

        rows = _parse_csv(result.twitter_profiles_csv)
        assert len(rows) == 10
        required = {"user_id", "name", "username", "user_char", "description"}
        for row in rows:
            assert set(row.keys()) == required
            assert row["name"] == "Alex Chen"

    @pytest.mark.asyncio
    async def test_produces_csuite_and_analyst_profiles(self, monkeypatch):
        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)

        result = await generate_agents(
            graph=_EMPTY_GRAPH,
            llm=llm,
            consumer_count=0,
            csuite_count=5,
            analyst_count=5,
        )

        rows = _parse_csv(result.twitter_profiles_csv)
        assert len(rows) == 10
        ids = [r["user_id"] for r in rows]
        # With consumer_count=0, first profiles are C-suite (c_XXX)
        assert ids[0].startswith("c_")
        # Analyst profiles have a_ prefix
        assert any(r["user_id"].startswith("a_") for r in rows)

    @pytest.mark.asyncio
    async def test_individual_failure_is_skipped(self, monkeypatch):
        call_count = 0

        async def flaky_complete(prompt, tier, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count in (3, 7, 15):
                from backend.llm.client import LLMRateLimitError
                raise LLMRateLimitError("rate limited")
            return _SAMPLE_PROFILE_JSON

        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)
        monkeypatch.setattr(llm, "complete", flaky_complete)

        result = await generate_agents(
            graph=_EMPTY_GRAPH,
            llm=llm,
            consumer_count=20,
            csuite_count=0,
            analyst_count=0,
        )

        rows = _parse_csv(result.twitter_profiles_csv)
        # 3 failures out of 20 = 17 profiles (85% ≥ 80% threshold)
        assert len(rows) == 17

    @pytest.mark.asyncio
    async def test_below_eighty_percent_raises_error(self, monkeypatch):
        async def mostly_fails(prompt, tier, **kwargs):
            if hash(prompt) % 3 != 0:
                from backend.llm.client import LLMRateLimitError
                raise LLMRateLimitError("rate limited")
            return _SAMPLE_PROFILE_JSON

        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)
        monkeypatch.setattr(llm, "complete", mostly_fails)

        with pytest.raises(AgentFactoryError, match="80%"):
            await generate_agents(
                graph=_EMPTY_GRAPH,
                llm=llm,
                consumer_count=20,
                csuite_count=0,
                analyst_count=0,
            )

    @pytest.mark.asyncio
    async def test_reddit_profiles_generated(self, monkeypatch):
        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)

        result = await generate_agents(
            graph=_EMPTY_GRAPH,
            llm=llm,
            consumer_count=5,
            csuite_count=0,
            analyst_count=0,
        )

        reddit = json.loads(result.reddit_profiles_json)
        assert isinstance(reddit, list)
        assert len(reddit) == 5
        assert "realname" in reddit[0] or "name" in reddit[0]


class TestGenerateAgentsSSE:
    @pytest.mark.asyncio
    async def test_stage_events_emitted(self, monkeypatch):
        from backend.pipeline.task_manager import task_manager

        task_manager.reset()
        sim_id = task_manager.init_sim()

        llm = MockLLMClient(default_response=_SAMPLE_PROFILE_JSON)

        await generate_agents(
            graph=_EMPTY_GRAPH,
            llm=llm,
            consumer_count=5,
            csuite_count=0,
            analyst_count=0,
            sim_id=sim_id,
        )

        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        event_names = [e["event"] for e in events]
        assert "stage_start" in event_names
        assert "stage_complete" in event_names
        complete = [e for e in events if e["event"] == "stage_complete"]
        assert complete[0]["data"]["agent_count"] == 5
