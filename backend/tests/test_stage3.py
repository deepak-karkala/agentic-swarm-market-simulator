"""Tests for Stage 3: Track 1 (OASIS) and Track 3 (Analyst Desk)."""

import json
import sqlite3

import pytest

from backend.llm.mock_client import MockLLMClient
from backend.stage0.seeder import RealitySeed
from backend.stage3.track1_oasis import Track1Result, _append_posts_jsonl, run_track1
from backend.stage3.track3_analyst import AnalystReport, generate_analyst_reports


# ── Track 3 test data ──

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

_VALID_JSON_BAD_CONVICTION = json.dumps({
    "analyst_name": "Jane Smith", "firm": "GS", "target_company": "Tesla",
    "earnings_revision_pct": -5.0, "price_target_revision_pct": -10.0,
    "thesis_update": "Risk.", "conviction": "impossible", "rating_change": "downgrade",
})

_VALID_JSON_MISSING_KEY = json.dumps({
    "analyst_name": "Jane Smith", "target_company": "Tesla",
    "earnings_revision_pct": -5.0, "price_target_revision_pct": -10.0,
    "thesis_update": "Risk.", "rating_change": "downgrade",
})


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


# ── Track 1 test data ──

_SAMPLE_PROFILES_CSV = (
    "user_id,name,username,user_char,description\n"
    "0,Alex Chen,alexchen_tech,Tech enthusiast.,Early adopter.\n"
    "1,Sarah Johnson,sarah_finance,Finance analyst.,Market watcher.\n"
    "2,Mike Rodriguez,mikerodriguez_cars,Auto journalist.,Car reviews.\n"
    "3,Emily Park,emilypark_news,Tech reporter.,Facts first.\n"
    "4,David Kim,davidkim_tesla,Tesla fan.,EV advocate.\n"
)


# ══════════════════════════════════════════════════════════════════════════════
# Track 3: Analyst Desk
# ══════════════════════════════════════════════════════════════════════════════

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
        assert len(reports) == 0

    @pytest.mark.asyncio
    async def test_valid_json_bad_conviction_retries_then_skips(self, monkeypatch):
        async def bad_conviction(prompt, tier, **kwargs):
            return _VALID_JSON_BAD_CONVICTION
        llm = MockLLMClient(default_response=_VALID_REPORT)
        monkeypatch.setattr(llm, "complete", bad_conviction)
        seed = _make_seed()
        reports = await generate_analyst_reports(seed, llm, analyst_count=2)
        assert len(reports) == 0

    @pytest.mark.asyncio
    async def test_missing_key_retries_then_skips(self, monkeypatch):
        async def missing_key(prompt, tier, **kwargs):
            return _VALID_JSON_MISSING_KEY
        llm = MockLLMClient(default_response=_VALID_REPORT)
        monkeypatch.setattr(llm, "complete", missing_key)
        seed = _make_seed()
        reports = await generate_analyst_reports(seed, llm, analyst_count=2)
        assert len(reports) == 0


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


# ══════════════════════════════════════════════════════════════════════════════
# Track 1: OASIS Social Simulation
# ══════════════════════════════════════════════════════════════════════════════

class TestTrack1Result:
    def test_default_result_is_failed(self):
        r = Track1Result()
        assert r.status == "failed"
        assert r.actions_jsonl_path is None

    def test_success_result(self):
        r = Track1Result(status="completed", actions_jsonl_path="/tmp/actions.jsonl", rounds=3)  # noqa: S108
        assert r.status == "completed"
        assert r.rounds == 3


class TestAppendPostsJsonl:
    def test_round_injected_per_record(self, tmp_path):
        db_path = tmp_path / "test.db"
        jsonl_path = tmp_path / "actions.jsonl"

        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE post (post_id INTEGER PRIMARY KEY, user_id INTEGER, content TEXT, created_at TEXT, num_likes INTEGER DEFAULT 0, num_shares INTEGER DEFAULT 0)")
        conn.execute("CREATE TABLE trace (user_id INTEGER, created_at TEXT, action TEXT, info TEXT)")
        conn.execute("INSERT INTO post VALUES (1, 0, 'Hello world', '2025-01-01', 2, 1)")
        conn.execute("INSERT INTO post VALUES (2, 1, 'Nice post!', '2025-01-01', 0, 0)")
        conn.execute("INSERT INTO trace VALUES (0, '2025-01-01', 'like_post', 'liked post 1')")
        conn.commit()
        conn.close()

        _append_posts_jsonl(db_path, jsonl_path, round_num=0)
        _append_posts_jsonl(db_path, jsonl_path, round_num=1)

        lines = jsonl_path.read_text().strip().split("\n")
        assert len(lines) >= 4

        records = [json.loads(line) for line in lines]
        rounds_seen = set(r["round"] for r in records)
        assert rounds_seen == {0, 1}
        for r in records:
            assert "agent_id" in r
            assert "action" in r


class TestRunTrack1:
    @pytest.mark.asyncio
    async def test_simulation_runs_and_exports_actions(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-for-test")
        monkeypatch.setattr("camel.models.ModelFactory.create", lambda **kw: type("M", (), {})())

        class FakeAgent:
            def __init__(self, agent_id): self.agent_id = agent_id

        class FakeAgentGraph:
            def get_agents(self, ids=None):
                agents = [FakeAgent(i) for i in range(5)]
                return [(a.agent_id, a) for a in agents]
            def get_agent(self, agent_id): return FakeAgent(agent_id)
            def get_num_nodes(self): return 5

        step_calls = []

        class FakeEnv:
            agent_graph = FakeAgentGraph()
            async def reset(self): pass
            async def step(self, actions): step_calls.append(actions)
            async def close(self): pass

        monkeypatch.setattr("oasis.make", lambda **kw: FakeEnv())

        async def _fake_gen(**kw):
            return FakeAgentGraph()

        monkeypatch.setattr("oasis.generate_twitter_agent_graph", _fake_gen)

        result = await run_track1(twitter_profiles_csv=_SAMPLE_PROFILES_CSV, rounds=3)
        assert result.status == "completed"
        assert result.rounds == 3
        assert result.agent_count == 5
        assert len(step_calls) == 4

    @pytest.mark.asyncio
    async def test_agent_count_derived_from_csv(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-for-test")
        monkeypatch.setattr("camel.models.ModelFactory.create", lambda **kw: type("M", (), {})())

        class FakeEnv:
            agent_graph = type("G", (), {"get_agents": lambda s, ids=None: [], "get_agent": lambda s, i: None})()
            async def reset(self): pass
            async def step(self, a): pass
            async def close(self): pass

        monkeypatch.setattr("oasis.make", lambda **kw: FakeEnv())

        async def _fg(**kw):
            return type("G", (), {"get_num_nodes": lambda s: 3})()

        monkeypatch.setattr("oasis.generate_twitter_agent_graph", _fg)

        result = await run_track1(twitter_profiles_csv=_SAMPLE_PROFILES_CSV, rounds=1)
        assert result.agent_count == 5

    @pytest.mark.asyncio
    async def test_track_events_emitted(self, monkeypatch):
        from backend.pipeline.task_manager import task_manager
        task_manager.reset()
        sim_id = task_manager.init_sim()
        monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-for-test")
        monkeypatch.setattr("camel.models.ModelFactory.create", lambda **kw: type("M", (), {})())

        class FakeEnv:
            agent_graph = type("G", (), {"get_agents": lambda s, ids=None: [], "get_agent": lambda s, i: None})()
            async def reset(self): pass
            async def step(self, a): pass
            async def close(self): pass

        monkeypatch.setattr("oasis.make", lambda **kw: FakeEnv())

        async def _fg(**kw):
            return type("G", (), {"get_num_nodes": lambda s: 5})()

        monkeypatch.setattr("oasis.generate_twitter_agent_graph", _fg)

        await run_track1(twitter_profiles_csv=_SAMPLE_PROFILES_CSV, rounds=2, sim_id=sim_id)
        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        names = [e["event"] for e in events]
        assert "track_start" in names
        assert "track_complete" in names
