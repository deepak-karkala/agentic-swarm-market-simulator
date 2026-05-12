"""Tests for full pipeline orchestration (Task 6.1)."""

import pytest

from backend.api.schemas import SimulateRequest
from backend.llm.mock_client import MockLLMClient
from backend.pipeline.task_manager import task_manager


class TestPipelineEndToEnd:
    @pytest.mark.asyncio
    async def test_full_pipeline_runs_all_stages(self, monkeypatch):
        """Verify all stages are called in order by the orchestrator."""
        calls = []

        async def mock_seeder(scenario, geography, vertical, llm, sim_id=None, timeout=120):
            calls.append("stage0")
            from backend.stage0.seeder import RealitySeed
            return RealitySeed(geography=geography, vertical=vertical, scenario=scenario)

        async def mock_graph(seed, llm, sim_id=None):
            calls.append("stage1")
            from backend.stage1.graph_builder import GraphResult
            return GraphResult(raw_context={"scenario": seed.scenario})

        async def mock_agents(graph, llm, consumer_count=200, csuite_count=50, analyst_count=10, sim_id=None):
            calls.append("stage2")
            from backend.stage2.agent_factory import AgentGenerationResult
            return AgentGenerationResult(
                twitter_profiles_csv="u_id,name,username,user_char,description\n0,A,a,x,y\n",
                reddit_profiles_json="[]",
                total_agents=consumer_count,
            )

        async def mock_stage3(seed, csv, llm, rounds=10, sim_id=None):
            calls.append("stage3")
            from backend.stage3 import Stage3Result
            return Stage3Result(stats=None)

        async def mock_panel(seed, stats, llm, sim_id=None, per_agent_timeout=90):
            calls.append("stage35")
            return {}

        async def mock_report(seed, stats, t2, t3, experts, llm, sim_id=None):
            calls.append("stage4")
            return {"executive_summary": "Test report"}

        def mock_quality(report, experts):
            calls.append("quality")
            return report

        monkeypatch.setattr("backend.stage0.seeder.run_seeder", mock_seeder)
        monkeypatch.setattr("backend.stage1.graph_builder.build_graph", mock_graph)
        monkeypatch.setattr("backend.stage2.agent_factory.generate_agents", mock_agents)
        monkeypatch.setattr("backend.stage3.run_stage3", mock_stage3)
        monkeypatch.setattr("backend.stage35.expert_panel.run_expert_panel", mock_panel)
        monkeypatch.setattr("backend.stage4.react_agent.synthesize_report", mock_report)
        monkeypatch.setattr("backend.pipeline.quality_eval.evaluate_quality", mock_quality)

        from backend.pipeline.orchestrator import run_pipeline_background

        req = SimulateRequest(scenario_text="Apple EV", geography="US", vertical="auto")
        task_manager.reset()
        sim_id = task_manager.init_sim()

        # Run in a thread (mimics BackgroundTasks)
        import threading
        t = threading.Thread(target=run_pipeline_background, args=(sim_id, req, MockLLMClient()))
        t.start()
        t.join(timeout=10)

        assert len(calls) == 7
        assert calls == ["stage0", "stage1", "stage2", "stage3", "stage35", "stage4", "quality"]

    @pytest.mark.asyncio
    async def test_lock_released_after_pipeline(self, monkeypatch):
        """TaskManager lock is released after pipeline completes (success or error)."""
        async def mock_seeder(scenario, geography, vertical, llm, sim_id=None, timeout=120):
            from backend.stage0.seeder import RealitySeed
            return RealitySeed(geography=geography, vertical=vertical, scenario=scenario)

        async def mock_graph(seed, llm, sim_id=None):
            from backend.stage1.graph_builder import GraphResult
            return GraphResult()

        async def mock_agents(graph, llm, **kw):
            from backend.stage2.agent_factory import AgentGenerationResult
            return AgentGenerationResult(twitter_profiles_csv="h\n0,A,a,x,y\n", reddit_profiles_json="[]", total_agents=0)

        async def mock_stage3(seed, csv, llm, **kw):
            from backend.stage3 import Stage3Result
            return Stage3Result()

        async def mock_panel(seed, stats, llm, sim_id=None, per_agent_timeout=90):
            return {}

        async def mock_report(seed, stats, t2, t3, experts, llm, sim_id=None):
            return {"executive_summary": "ok"}

        def mock_quality(report, experts):
            return report

        monkeypatch.setattr("backend.stage0.seeder.run_seeder", mock_seeder)
        monkeypatch.setattr("backend.stage1.graph_builder.build_graph", mock_graph)
        monkeypatch.setattr("backend.stage2.agent_factory.generate_agents", mock_agents)
        monkeypatch.setattr("backend.stage3.run_stage3", mock_stage3)
        monkeypatch.setattr("backend.stage35.expert_panel.run_expert_panel", mock_panel)
        monkeypatch.setattr("backend.stage4.react_agent.synthesize_report", mock_report)
        monkeypatch.setattr("backend.pipeline.quality_eval.evaluate_quality", mock_quality)

        from backend.pipeline.orchestrator import run_pipeline_background

        req = SimulateRequest(scenario_text="Test", geography="US", vertical="auto")
        task_manager.reset()
        sim_id = task_manager.init_sim()
        task_manager.acquire()  # mimic the route acquiring the lock

        import threading
        t = threading.Thread(target=run_pipeline_background, args=(sim_id, req, MockLLMClient()))
        t.start()
        t.join(timeout=10)

        # Lock should be released
        assert task_manager.is_running is False
