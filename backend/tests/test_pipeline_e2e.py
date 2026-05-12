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
                total_agents=1,
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

        import threading
        t = threading.Thread(target=run_pipeline_background, args=(sim_id, req, MockLLMClient()))
        t.start()
        t.join(timeout=10)

        assert calls == ["stage0", "stage1", "stage2", "stage3", "stage35", "stage4", "quality"]

    @pytest.mark.asyncio
    async def test_lock_released_after_success(self, monkeypatch):
        """TaskManager lock is released after pipeline completes."""
        async def mock_seeder(*a, **kw):
            from backend.stage0.seeder import RealitySeed
            return RealitySeed(geography="US", vertical="auto", scenario="T")

        async def mock_graph(*a, **kw):
            from backend.stage1.graph_builder import GraphResult
            return GraphResult()

        async def mock_agents(*a, **kw):
            from backend.stage2.agent_factory import AgentGenerationResult
            return AgentGenerationResult(twitter_profiles_csv="h\n0,A,a,x,y\n", reddit_profiles_json="[]", total_agents=1)

        async def mock_stage3(*a, **kw):
            from backend.stage3 import Stage3Result
            return Stage3Result()

        async def mock_panel(*a, **kw):
            return {}

        async def mock_report(*a, **kw):
            return {"executive_summary": "ok"}

        def mock_quality(*a, **kw):
            return {"executive_summary": "ok"}

        monkeypatch.setattr("backend.stage0.seeder.run_seeder", mock_seeder)
        monkeypatch.setattr("backend.stage1.graph_builder.build_graph", mock_graph)
        monkeypatch.setattr("backend.stage2.agent_factory.generate_agents", mock_agents)
        monkeypatch.setattr("backend.stage3.run_stage3", mock_stage3)
        monkeypatch.setattr("backend.stage35.expert_panel.run_expert_panel", mock_panel)
        monkeypatch.setattr("backend.stage4.react_agent.synthesize_report", mock_report)
        monkeypatch.setattr("backend.pipeline.quality_eval.evaluate_quality", mock_quality)

        from backend.pipeline.orchestrator import run_pipeline_background

        req = SimulateRequest(scenario_text="T", geography="US", vertical="auto")
        task_manager.reset()
        sim_id = task_manager.init_sim()
        task_manager.acquire()

        import threading
        t = threading.Thread(target=run_pipeline_background, args=(sim_id, req, MockLLMClient()))
        t.start()
        t.join(timeout=10)

        assert task_manager.is_running is False

    @pytest.mark.asyncio
    async def test_pipeline_failure_emits_simulation_error(self, monkeypatch):
        """When a stage raises, the SSE stream gets simulation_error and lock releases."""
        async def failing_seeder(*a, **kw):
            raise RuntimeError("Stage 0 crash")

        monkeypatch.setattr("backend.stage0.seeder.run_seeder", failing_seeder)

        from backend.pipeline.orchestrator import run_pipeline_background

        req = SimulateRequest(scenario_text="T", geography="US", vertical="auto")
        task_manager.reset()
        sim_id = task_manager.init_sim()

        import threading
        t = threading.Thread(target=run_pipeline_background, args=(sim_id, req, MockLLMClient()))
        t.start()
        t.join(timeout=10)

        queue = task_manager.get_queue(sim_id)
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())

        error_events = [e for e in events if e["event"] == "simulation_error"]
        assert len(error_events) >= 1
        assert task_manager.is_running is False

    @pytest.mark.asyncio
    async def test_report_persisted_after_completion(self, monkeypatch):
        """Report is stored in task_manager and retrievable after pipeline completes."""
        async def mock_seeder(*a, **kw):
            from backend.stage0.seeder import RealitySeed
            return RealitySeed(geography="US", vertical="auto", scenario="T")

        async def mock_graph(*a, **kw):
            from backend.stage1.graph_builder import GraphResult
            return GraphResult()

        async def mock_agents(*a, **kw):
            from backend.stage2.agent_factory import AgentGenerationResult
            return AgentGenerationResult(twitter_profiles_csv="h\n0,A,a,x,y\n", reddit_profiles_json="[]", total_agents=1)

        async def mock_stage3(*a, **kw):
            from backend.stage3 import Stage3Result
            return Stage3Result()

        async def mock_panel(*a, **kw):
            return {}

        async def mock_report(*a, **kw):
            return {"executive_summary": "Final report content"}

        def mock_quality(r, e):
            return r

        monkeypatch.setattr("backend.stage0.seeder.run_seeder", mock_seeder)
        monkeypatch.setattr("backend.stage1.graph_builder.build_graph", mock_graph)
        monkeypatch.setattr("backend.stage2.agent_factory.generate_agents", mock_agents)
        monkeypatch.setattr("backend.stage3.run_stage3", mock_stage3)
        monkeypatch.setattr("backend.stage35.expert_panel.run_expert_panel", mock_panel)
        monkeypatch.setattr("backend.stage4.react_agent.synthesize_report", mock_report)
        monkeypatch.setattr("backend.pipeline.quality_eval.evaluate_quality", mock_quality)

        from backend.pipeline.orchestrator import run_pipeline_background

        req = SimulateRequest(scenario_text="T", geography="US", vertical="auto")
        task_manager.reset()
        sim_id = task_manager.init_sim()

        import threading
        t = threading.Thread(target=run_pipeline_background, args=(sim_id, req, MockLLMClient()))
        t.start()
        t.join(timeout=10)

        stored = task_manager.get_report(sim_id)
        assert stored is not None
        assert stored["executive_summary"] == "Final report content"
