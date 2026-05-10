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
        # Round 1: "amazing" "Love" → positive CREATE_POST, 1 like, 1 repost
        assert r1["positive_pct"] > r1["negative_pct"]
        assert r1["positive_pct"] + r1["negative_pct"] + r1["neutral_pct"] == pytest.approx(100.0, abs=5)

    def test_inflection_points(self, tmp_path):
        path = _write_jsonl(tmp_path / "actions.jsonl", _SAMPLE_JSONL)
        stats = SimulationStats.aggregate(path)

        # Round 2 is negative ("terrible", "Hate"), Round 3 is positive → inflection
        assert len(stats.inflection_points) >= 1
        inflection = stats.inflection_points[0]
        assert "round" in inflection

    def test_adoption_proxy(self, tmp_path):
        path = _write_jsonl(tmp_path / "actions.jsonl", _SAMPLE_JSONL)
        stats = SimulationStats.aggregate(path)

        assert "early_adopters_pct" in stats.adoption_proxy
        assert "mainstream_pct" in stats.adoption_proxy
        assert "laggards_pct" in stats.adoption_proxy

    def test_top_content(self, tmp_path):
        path = _write_jsonl(tmp_path / "actions.jsonl", _SAMPLE_JSONL)
        stats = SimulationStats.aggregate(path)

        assert len(stats.top_content) <= 10
        assert len(stats.top_content) >= 1
        # Post 3 (round 3) has most engagement (10 likes + 5 shares)
        top = stats.top_content[0]
        assert top["post_id"] == 3
        assert top["likes"] == 10

    def test_agent_group_summary(self, tmp_path):
        path = _write_jsonl(tmp_path / "actions.jsonl", _SAMPLE_JSONL)
        stats = SimulationStats.aggregate(path)

        assert "consumer" in stats.agent_group_summary
        assert stats.agent_group_summary["consumer"] > 0

    def test_empty_jsonl_produces_minimal_stats(self, tmp_path):
        path = _write_jsonl(tmp_path / "actions.jsonl", "")
        stats = SimulationStats.aggregate(path)

        assert stats.total_rounds == 0
        assert stats.per_round_sentiment == []
        assert stats.inflection_points == []
