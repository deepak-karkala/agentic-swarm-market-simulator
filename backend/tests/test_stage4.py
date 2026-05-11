"""Tests for Stage 4: ReACT Synthesizer."""

import pytest

from backend.llm.mock_client import MockLLMClient
from backend.pipeline.sim_stats import SimulationStats
from backend.stage0.seeder import RealitySeed
from backend.stage3.track2_boardroom import BoardroomDecision, BoardroomResult
from backend.stage3.track3_analyst import AnalystReport
from backend.stage35.expert_panel import ExpertAnalysis
from backend.stage4.react_agent import synthesize_report


_FAKE_REPORT_SECTION = "This is a synthetic report section generated from simulation data."

REQUIRED_SECTIONS = [
    "executive_summary",
    "public_narrative",
    "competitive_response",
    "financial_impact",
    "consumer_adoption",
    "strategic_recommendations",
    "competitive_landscape",
    "regulatory",
    "kol_impact",
    "methodology",
]


def _make_seed() -> RealitySeed:
    seed = RealitySeed(geography="US", vertical="auto", scenario="Apple EV")
    seed.competitors = [{"name": "Tesla"}]
    seed.kols = [{"name": "Elon Musk"}]
    seed.macro = {"rate": "5.5%"}
    return seed


def _make_stats() -> SimulationStats:
    return SimulationStats(
        total_rounds=10,
        per_round_sentiment=[{"round": 1, "positive_pct": 60, "negative_pct": 20, "neutral_pct": 20}],
        adoption_proxy={"early_adopters_pct": 40, "mainstream_pct": 35, "laggards_pct": 25},
        top_content=[],
        inflection_points=[],
        agent_group_summary={"consumer": 200},
    )


def _make_track2() -> BoardroomResult:
    return BoardroomResult(
        status="completed",
        camel_used=False,
        decisions=[BoardroomDecision(
            competitor="Tesla", action_type="price_cut",
            timeline="immediate", stated_rationale="Defend share.",
        )],
    )


def _make_track3() -> list[AnalystReport]:
    return [
        AnalystReport(
            analyst_name="Jane", firm="GS", target_company="Tesla",
            earnings_revision_pct=-5.0, price_target_revision_pct=-10.0,
            thesis_update="Risk.", conviction="high", rating_change="downgrade",
        ),
    ]


def _make_experts() -> dict[str, ExpertAnalysis]:
    return {
        name: ExpertAnalysis(summary=f"{name} analysis.", key_findings=["F1", "F2"], confidence="high")
        for name in ("competitive", "economic", "consumer", "domain", "regulatory")
    }


class TestSynthesizeReport:
    @pytest.mark.asyncio
    async def test_all_sections_produced(self, monkeypatch):
        llm = MockLLMClient(default_response=_FAKE_REPORT_SECTION)
        report = await synthesize_report(
            _make_seed(), _make_stats(), _make_track2(), _make_track3(), _make_experts(), llm,
        )

        for section in REQUIRED_SECTIONS:
            assert section in report, f"Missing section: {section}"
            assert isinstance(report[section], str)
            assert len(report[section]) > 0

    @pytest.mark.asyncio
    async def test_empty_llm_response_gets_placeholder(self, monkeypatch):
        llm = MockLLMClient(default_response="")

        report = await synthesize_report(
            _make_seed(), _make_stats(), _make_track2(), _make_track3(), _make_experts(), llm,
        )

        assert "[Section" in report["executive_summary"] or "Insufficient" in report["executive_summary"]
        # Never silently absent — every section must have content
        for section in REQUIRED_SECTIONS:
            assert len(report[section]) > 0

    @pytest.mark.asyncio
    async def test_missing_track2_produces_section(self, monkeypatch):
        """When Track 2 is None, the competitive_response section still exists (not silently missing)."""
        llm = MockLLMClient(default_response=_FAKE_REPORT_SECTION)

        report = await synthesize_report(
            _make_seed(), _make_stats(), None, _make_track3(), _make_experts(), llm,
        )

        # Section must exist — never silently absent
        assert "competitive_response" in report
        assert len(report["competitive_response"]) > 0

    @pytest.mark.asyncio
    async def test_sse_events_emitted(self, monkeypatch):
        from backend.pipeline.task_manager import task_manager

        task_manager.reset()
        sim_id = task_manager.init_sim()

        llm = MockLLMClient(default_response=_FAKE_REPORT_SECTION)
        await synthesize_report(
            _make_seed(), _make_stats(), _make_track2(), _make_track3(), _make_experts(), llm,
            sim_id=sim_id,
        )

        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        names = [e["event"] for e in events]
        assert "stage_start" in names
        assert "stage_complete" in names
        section_events = [e for e in events if e["event"] == "section_complete"]
        assert len(section_events) >= 8
