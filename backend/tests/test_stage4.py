"""Tests for Stage 4: ReACT Synthesizer + Quality Evaluator."""

import pytest

from backend.llm.mock_client import MockLLMClient
from backend.pipeline.quality_eval import evaluate_quality
from backend.pipeline.sim_stats import SimulationStats
from backend.stage0.seeder import RealitySeed
from backend.stage3.track2_boardroom import BoardroomDecision, BoardroomResult
from backend.stage3.track3_analyst import AnalystReport
from backend.stage35.expert_panel import ExpertAnalysis
from backend.stage4.react_agent import synthesize_report


_FAKE_REPORT_SECTION = "This is a synthetic report section generated from simulation data."

REQUIRED_SECTIONS = [
    "executive_summary", "public_narrative", "competitive_response",
    "financial_impact", "consumer_adoption", "strategic_recommendations",
    "competitive_landscape", "regulatory", "kol_impact", "methodology",
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
        top_content=[], inflection_points=[], agent_group_summary={"consumer": 200},
    )


def _make_track2() -> BoardroomResult:
    return BoardroomResult(status="completed", camel_used=False, decisions=[
        BoardroomDecision(competitor="Tesla", action_type="price_cut", timeline="immediate", stated_rationale="Defend share."),
    ])


def _make_track3() -> list[AnalystReport]:
    return [AnalystReport(analyst_name="Jane", firm="GS", target_company="Tesla", earnings_revision_pct=-5.0, price_target_revision_pct=-10.0, thesis_update="Risk.", conviction="high", rating_change="downgrade")]


def _make_experts() -> dict[str, ExpertAnalysis]:
    return {name: ExpertAnalysis(summary=f"{name} analysis.", key_findings=["F1", "F2"], confidence="high") for name in ("competitive", "economic", "consumer", "domain", "regulatory")}


# ══════════════════════════════════════════════════════════════════════════════
# Stage 4: Report Synthesis
# ══════════════════════════════════════════════════════════════════════════════

class TestSynthesizeReport:
    @pytest.mark.asyncio
    async def test_all_sections_produced(self, monkeypatch):
        llm = MockLLMClient(default_response=_FAKE_REPORT_SECTION)
        report = await synthesize_report(_make_seed(), _make_stats(), _make_track2(), _make_track3(), _make_experts(), llm)
        for section in REQUIRED_SECTIONS:
            assert section in report, f"Missing section: {section}"
            assert len(report[section]) > 0

    @pytest.mark.asyncio
    async def test_empty_llm_response_gets_placeholder(self, monkeypatch):
        llm = MockLLMClient(default_response="")
        report = await synthesize_report(_make_seed(), _make_stats(), _make_track2(), _make_track3(), _make_experts(), llm)
        for section in REQUIRED_SECTIONS:
            assert len(report[section]) > 0

    @pytest.mark.asyncio
    async def test_missing_track2_produces_section(self, monkeypatch):
        llm = MockLLMClient(default_response=_FAKE_REPORT_SECTION)
        report = await synthesize_report(_make_seed(), _make_stats(), None, _make_track3(), _make_experts(), llm)
        assert "competitive_response" in report
        assert len(report["competitive_response"]) > 0

    @pytest.mark.asyncio
    async def test_llm_exception_produces_placeholder(self, monkeypatch):
        async def raises_on_first(prompt, tier, **kwargs):
            raise RuntimeError("LLM crash")
        llm = MockLLMClient(default_response=_FAKE_REPORT_SECTION)
        monkeypatch.setattr(llm, "complete", raises_on_first)
        report = await synthesize_report(_make_seed(), _make_stats(), _make_track2(), _make_track3(), _make_experts(), llm)
        for section in REQUIRED_SECTIONS:
            assert section in report
            assert len(report[section]) > 0

    @pytest.mark.asyncio
    async def test_first_call_empty_retry_succeeds(self, monkeypatch):
        call_count = 0
        async def empty_then_ok(prompt, tier, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 10:
                return ""
            return _FAKE_REPORT_SECTION
        llm = MockLLMClient(default_response=_FAKE_REPORT_SECTION)
        monkeypatch.setattr(llm, "complete", empty_then_ok)
        report = await synthesize_report(_make_seed(), _make_stats(), _make_track2(), _make_track3(), _make_experts(), llm)
        for section in REQUIRED_SECTIONS:
            assert len(report[section]) > 0
        assert call_count > 10

    @pytest.mark.asyncio
    async def test_sse_events_emitted(self, monkeypatch):
        from backend.pipeline.task_manager import task_manager
        task_manager.reset()
        sim_id = task_manager.init_sim()
        llm = MockLLMClient(default_response=_FAKE_REPORT_SECTION)
        await synthesize_report(_make_seed(), _make_stats(), _make_track2(), _make_track3(), _make_experts(), llm, sim_id=sim_id)
        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        section_events = [e for e in events if e["event"] == "section_complete"]
        assert len(section_events) == 10


# ══════════════════════════════════════════════════════════════════════════════
# Quality Evaluator (Task 5.1)
# ══════════════════════════════════════════════════════════════════════════════

_VALID_SECTION = "Based on simulation data from Round 3, consumer sentiment showed a significant positive shift with 200 agents participating."
_UNSOURCED_PRECISION = "The market share will drop by exactly 7.3% within 6 months. Tesla stock will decline 15%."
_EXPERT_PERSONA = (
    "According to our McKinsey-persona competitive strategy agent, "
    "the market will be disrupted. Based on 200 agents across Round 4."
)
_PLACEHOLDER_SECTION = "[Section]: Insufficient simulation data — consider increasing agent count."
_DOLLAR_CLAIM = "The investment required is $50M for the first phase."
_STOCK_DIRECTION = "The stock will decline sharply after the announcement."
_MIXED_SOURCED_AND_UNSOURCED = (
    "Revenue will grow 25% next year (Round 3, 150 agents). "
    + ("More analysis continues here with additional context " * 8)
    + "Costs will rise 10% without any clear data source."
)


class TestQualityEval:
    def test_valid_section_passes(self):
        report = {"executive_summary": _VALID_SECTION}
        result = evaluate_quality(report, experts=None)
        assert "QUALITY FLAG" not in result["executive_summary"]

    def test_unsourced_precision_flagged(self):
        report = {"executive_summary": _UNSOURCED_PRECISION}
        result = evaluate_quality(report, experts=None)
        assert "QUALITY FLAG" in result["executive_summary"]

    def test_expert_persona_without_expert_data_flagged(self):
        report = {"competitive_landscape": _EXPERT_PERSONA}
        result = evaluate_quality(report, experts=None)
        assert "QUALITY FLAG" in result["competitive_landscape"]

    def test_expert_persona_with_expert_data_passes(self):
        experts = {"competitive": ExpertAnalysis(summary="OK.", key_findings=["F1"], confidence="high")}
        report = {"competitive_landscape": _EXPERT_PERSONA}
        result = evaluate_quality(report, experts=experts)
        assert "QUALITY FLAG" not in result["competitive_landscape"]

    def test_placeholder_section_passes(self):
        report = {"executive_summary": _PLACEHOLDER_SECTION}
        result = evaluate_quality(report, experts=None)
        assert "QUALITY FLAG" not in result["executive_summary"]

    def test_empty_experts_handled(self):
        report = {"competitive_landscape": _EXPERT_PERSONA}
        result = evaluate_quality(report, experts={})
        assert "QUALITY FLAG" in result["competitive_landscape"]

    def test_dollar_claim_flagged(self):
        report = {"executive_summary": _DOLLAR_CLAIM}
        result = evaluate_quality(report, experts=None)
        assert "QUALITY FLAG" in result["executive_summary"]

    def test_stock_direction_flagged(self):
        report = {"financial_impact": _STOCK_DIRECTION}
        result = evaluate_quality(report, experts=None)
        assert "QUALITY FLAG" in result["financial_impact"]

    def test_sourced_number_next_to_unsourced_is_flagged(self):
        """One cited number doesn't source all numbers in the section."""
        report = {"executive_summary": _MIXED_SOURCED_AND_UNSOURCED}
        result = evaluate_quality(report, experts=None)
        assert "QUALITY FLAG" in result["executive_summary"]

    def test_wrong_expert_key_still_flags(self):
        """Regulatory expert present but competitive persona referenced → flagged."""
        experts = {"regulatory": ExpertAnalysis(summary="OK.", key_findings=["F1"], confidence="high")}
        report = {"competitive_landscape": _EXPERT_PERSONA}
        result = evaluate_quality(report, experts=experts)
        assert "QUALITY FLAG" in result["competitive_landscape"]

    def test_low_confidence_expert_flagged(self):
        """Expert exists but confidence='low' → still flagged."""
        experts = {"competitive": ExpertAnalysis(summary="Weak.", key_findings=[], confidence="low")}
        report = {"competitive_landscape": _EXPERT_PERSONA}
        result = evaluate_quality(report, experts=experts)
        assert "QUALITY FLAG" in result["competitive_landscape"]
