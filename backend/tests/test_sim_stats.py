"""Tests for SimulationStats aggregator."""

from pathlib import Path

import pytest

from backend.pipeline.sim_stats import SimulationStats


_SAMPLE_JSONL = """\
{"agent_id": "u_000", "action": "CREATE_POST", "content": "Apple EV is amazing! Love it.", "round": 1, "timestamp": 0, "post_id": 1, "num_likes": 5, "num_shares": 3}
{"agent_id": "u_001", "action": "LIKE_POST", "content": "", "round": 1, "timestamp": 0, "post_id": 1, "num_likes": 0, "num_shares": 0}
{"agent_id": "u_002", "action": "REPOST", "content": "", "round": 1, "timestamp": 0, "post_id": 1, "num_likes": 0, "num_shares": 0}
{"agent_id": "u_003", "action": "DO_NOTHING", "content": "", "round": 1, "timestamp": 0}
{"agent_id": "u_000", "action": "CREATE_POST", "content": "Apple EV is terrible! Hate it.", "round": 2, "timestamp": 0, "post_id": 2, "num_likes": 1, "num_shares": 0}
{"agent_id": "u_001", "action": "LIKE_POST", "content": "", "round": 2, "timestamp": 0, "post_id": 2, "num_likes": 0, "num_shares": 0}
{"agent_id": "u_002", "action": "LIKE_POST", "content": "", "round": 2, "timestamp": 0, "post_id": 2, "num_likes": 0, "num_shares": 0}
{"agent_id": "u_003", "action": "REPOST", "content": "", "round": 2, "timestamp": 0, "post_id": 2}
{"agent_id": "u_004", "action": "REPOST", "content": "", "round": 2, "timestamp": 0, "post_id": 2}
{"agent_id": "u_000", "action": "CREATE_POST", "content": "Actually, Apple EV could be decent.", "round": 3, "timestamp": 0, "post_id": 3, "num_likes": 10, "num_shares": 5}
{"agent_id": "u_001", "action": "LIKE_POST", "content": "", "round": 3, "timestamp": 0, "post_id": 3, "num_likes": 0, "num_shares": 0}
{"agent_id": "u_002", "action": "LIKE_POST", "content": "", "round": 3, "timestamp": 0, "post_id": 3, "num_likes": 0, "num_shares": 0}
{"agent_id": "u_005", "action": "CREATE_POST", "content": "Looking forward to the Apple EV!", "round": 3, "timestamp": 0, "post_id": 4, "num_likes": 8, "num_shares": 2}
{"agent_id": "u_006", "action": "FOLLOW", "content": "", "round": 3, "timestamp": 0}
"""

# Fixture where negative sentiment shift triggers the inflection (not positive)
_NEGATIVE_INFLECTION_JSONL = """\
{"agent_id": "u_000", "action": "CREATE_POST", "content": "Apple EV is excellent!", "round": 1, "post_id": 1, "num_likes": 3, "num_shares": 1}
{"agent_id": "u_001", "action": "LIKE_POST", "round": 1, "post_id": 1}
{"agent_id": "u_002", "action": "LIKE_POST", "round": 1, "post_id": 1}
{"agent_id": "u_003", "action": "LIKE_POST", "round": 1, "post_id": 1}
{"agent_id": "u_000", "action": "CREATE_POST", "content": "Apple EV is a disaster! Sell now!", "round": 2, "post_id": 2, "num_likes": 5, "num_shares": 4}
{"agent_id": "u_001", "action": "LIKE_POST", "round": 2, "post_id": 2}
{"agent_id": "u_004", "action": "REPOST", "round": 2, "post_id": 2}
{"agent_id": "u_005", "action": "REPOST", "round": 2, "post_id": 2}
"""

# Multi-agent-type fixture
_MIXED_AGENTS_JSONL = """\
{"agent_id": "u_000", "action": "CREATE_POST", "content": "Excited!", "round": 1, "post_id": 1, "num_likes": 2, "num_shares": 1}
{"agent_id": "c_000", "action": "CREATE_POST", "content": "We will defend.", "round": 1, "post_id": 2, "num_likes": 0, "num_shares": 0}
{"agent_id": "a_000", "action": "CREATE_POST", "content": "Neutral outlook.", "round": 1, "post_id": 3, "num_likes": 0, "num_shares": 0}
"""


def _write_jsonl(path: Path, content: str) -> Path:
    path.write_text(content.strip())
    return path


class TestSimulationStats:
    def test_total_rounds(self, tmp_path):
        path = _write_jsonl(tmp_path / "actions.jsonl", _SAMPLE_JSONL)
        stats = SimulationStats.aggregate(path)
        assert stats.total_rounds == 3

    def test_per_round_sentiment(self, tmp_path):
        path = _write_jsonl(tmp_path / "actions.jsonl", _SAMPLE_JSONL)
        stats = SimulationStats.aggregate(path)

        assert len(stats.per_round_sentiment) == 3
        r1 = stats.per_round_sentiment[0]
        assert r1["round"] == 1
        assert r1["positive_pct"] > r1["negative_pct"]
        assert r1["positive_pct"] + r1["negative_pct"] + r1["neutral_pct"] == pytest.approx(100.0, abs=5)

    def test_negative_inflection_detected_correctly(self, tmp_path):
        """Negative sentiment jump drives the inflection, not positive."""
        path = _write_jsonl(tmp_path / "actions.jsonl", _NEGATIVE_INFLECTION_JSONL)
        stats = SimulationStats.aggregate(path)

        assert len(stats.inflection_points) == 1
        infl = stats.inflection_points[0]
        assert infl["round"] == 2
        assert infl["caused_by"] == "negative"
        assert infl["shift_pct"] > 20

    def test_adoption_proxy_deduplicates_agents(self, tmp_path):
        path = _write_jsonl(tmp_path / "actions.jsonl", _SAMPLE_JSONL)
        stats = SimulationStats.aggregate(path)

        assert "early_adopters_pct" in stats.adoption_proxy
        assert "mainstream_pct" in stats.adoption_proxy
        assert "laggards_pct" in stats.adoption_proxy
        # Percentages should sum to ~100 (mutually exclusive, one level per agent)
        ad = stats.adoption_proxy
        total = ad["early_adopters_pct"] + ad["mainstream_pct"] + ad["laggards_pct"]
        assert total == pytest.approx(100.0, abs=0.5)

    def test_top_content(self, tmp_path):
        path = _write_jsonl(tmp_path / "actions.jsonl", _SAMPLE_JSONL)
        stats = SimulationStats.aggregate(path)

        assert len(stats.top_content) <= 10
        assert len(stats.top_content) >= 1
        top = stats.top_content[0]
        assert top["post_id"] == 3
        assert top["likes"] == 10

    def test_agent_group_summary_by_prefix(self, tmp_path):
        path = _write_jsonl(tmp_path / "actions.jsonl", _MIXED_AGENTS_JSONL)
        stats = SimulationStats.aggregate(path)

        assert stats.agent_group_summary["consumer"] == 1
        assert stats.agent_group_summary["competitor"] == 1
        assert stats.agent_group_summary["analyst"] == 1

    def test_empty_jsonl_produces_minimal_stats(self, tmp_path):
        path = _write_jsonl(tmp_path / "actions.jsonl", "")
        stats = SimulationStats.aggregate(path)

        assert stats.total_rounds == 0
        assert stats.per_round_sentiment == []
        assert stats.inflection_points == []
        assert stats.agent_group_summary == {}
