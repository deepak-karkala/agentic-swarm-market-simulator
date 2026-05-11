import { useState, useCallback } from "react";
import { useSimulation, type SimStatus } from "../hooks/useSimulation";
import { Pane } from "../components/Pane/Pane";
import { Button } from "../components/Button/Button";
import { Chip } from "../components/Chip/Chip";
import { LiveDot } from "../components/LiveDot/LiveDot";
import { ProgressBar } from "../components/ProgressBar/ProgressBar";
import { StageRow } from "../components/StageRow/StageRow";
import styles from "./SimulatorPage.module.css";

const EXAMPLE_SCENARIOS = [
  "Apple launches an electric vehicle at $35,000",
  "TikTok ban goes into effect in the US",
  "FDA approves Ozempic for over-the-counter use",
];

export function SimulatorPage() {
  const { state, dispatch, startSimulation } = useSimulation();
  const [scenarioText, setScenarioText] = useState("");
  const [geography, setGeography] = useState("US");
  const [vertical, setVertical] = useState("auto");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const handleRun = useCallback(async () => {
    if (!scenarioText.trim()) return;
    try {
      const resp = await fetch("/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          scenario_text: scenarioText,
          geography,
          vertical,
          horizon_days: 30,
          agent_count: 100,
        }),
      });
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({ detail: {} }));
        const msg: string = detail?.detail?.error ?? `Server error (${resp.status})`;
        dispatch({ type: "simulation_error", message: msg });
        return;
      }
      const data = await resp.json();
      startSimulation(data.sim_id);
    } catch {
      // Network error — backend not available, use mock for dev
      startSimulation("mock-001");
    }
  }, [scenarioText, geography, vertical, startSimulation, dispatch]);

  const stageList: { stage: string; label: string }[] = [
    { stage: "stage0", label: "0\u00B7Seed \u2014 Reality Seeding" },
    { stage: "stage1", label: "1\u00B7Graph \u2014 Building knowledge graph" },
    { stage: "stage2", label: "2\u00B7Agents \u2014 Creating personas" },
    { stage: "stage3", label: "3\u00B7Simulate \u2014 Running tracks" },
    { stage: "stage35", label: "3.5\u00B7Expert Panel" },
    { stage: "stage4", label: "4\u00B7Report \u2014 Synthesizing" },
  ];

  function getStageStatus(stage: string): "done" | "run" | "idle" {
    if (state.status === "INPUT" || state.status === "ERROR") return "idle";
    const order = stageList.map((s) => s.stage);
    const currentIdx = order.indexOf(state.currentStage);
    const stageIdx = order.indexOf(stage);
    if (currentIdx < 0) return "idle";
    if (stageIdx < currentIdx) return "done";
    if (stageIdx === currentIdx) return "run";
    return "idle";
  }

  function renderStatusChip(): React.ReactNode {
    const map: Record<SimStatus, { label: string; variant: "accent" | "positive" | "negative" | "default" }> = {
      INPUT: { label: "READY", variant: "default" },
      STAGE0: { label: "SEEDING", variant: "accent" },
      STAGE1: { label: "GRAPH", variant: "accent" },
      STAGE2: { label: "AGENTS", variant: "accent" },
      RUNNING: { label: "RUNNING", variant: "accent" },
      PAUSED: { label: "PAUSED", variant: "accent" },
      REPORT: { label: "COMPLETE", variant: "positive" },
      ERROR: { label: "ERROR", variant: "negative" },
    };
    const s = map[state.status];
    return <Chip variant={s.variant}>{s.label}</Chip>;
  }

  return (
    <div className={styles.page}>
      {!sidebarCollapsed && (
        <aside className={styles.sidebar}>
          <div className={styles.sidebarHeader}>
            <span>SCENARIO</span>
            <button type="button" className={styles.collapseBtn} onClick={() => setSidebarCollapsed(true)}>
              {"\u25C0"}
            </button>
          </div>

          <textarea
            className={styles.scenarioInput}
            rows={4}
            placeholder="Describe your business scenario..."
            value={scenarioText}
            onChange={(e) => setScenarioText(e.target.value)}
            disabled={state.status !== "INPUT"}
          />

          <div className={styles.paramRow}>
            <select value={geography} onChange={(e) => setGeography(e.target.value)} className={styles.select}>
              <option value="US">US</option>
              <option value="EU">EU</option>
              <option value="India">India</option>
              <option value="China">China</option>
              <option value="Global">Global</option>
            </select>
            <select value={vertical} onChange={(e) => setVertical(e.target.value)} className={styles.select}>
              <option value="auto">Auto</option>
              <option value="pharma">Pharma</option>
              <option value="fintech">Fintech</option>
              <option value="consumer_electronics">Consumer Electronics</option>
              <option value="energy">Energy</option>
            </select>
          </div>

          <Button
            variant="primary"
            onClick={handleRun}
            disabled={state.status !== "INPUT" || !scenarioText.trim()}
          >
            {"\u25B6"} RUN SIMULATION
          </Button>

          {state.status !== "INPUT" && (
            <div className={styles.costMeter}>
              ${state.costUsd.toFixed(2)} / $10.00
            </div>
          )}

          {(state.status === "INPUT" || state.status === "ERROR") && (
            <div className={styles.examples}>
              <span className={styles.examplesLabel}>Try a scenario:</span>
              {EXAMPLE_SCENARIOS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className={styles.exampleBtn}
                  onClick={() => setScenarioText(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          <div className={styles.stages}>
            {stageList.map((s) => (
              <StageRow key={s.stage} status={getStageStatus(s.stage)} label={s.label} />
            ))}
          </div>
        </aside>
      )}

      {sidebarCollapsed && (
        <button type="button" className={styles.expandBtn} onClick={() => setSidebarCollapsed(false)}>
          {"\u25B6"}
        </button>
      )}

      <main className={styles.main}>
        <div className={styles.topBar}>
          {state.simId && <Chip variant="accent">SIM #{state.simId}</Chip>}
          <span className={styles.scenarioTitle}>{scenarioText.slice(0, 50) || "No scenario configured"}</span>
          {state.status === "RUNNING" && (
            <>
              <span>Round {state.round}/{state.totalRounds}</span>
              <LiveDot pulse />
            </>
          )}
          <span style={{ marginLeft: "auto" }}>{renderStatusChip()}</span>
        </div>

        <div className={styles.progress}>
          <ProgressBar
            value={stageList.findIndex((s) => s.stage === state.currentStage) >= 0
              ? ((stageList.findIndex((s) => s.stage === state.currentStage) + 1) / stageList.length) * 100
              : 0}
          />
        </div>

        <div className={styles.content}>
          {state.status === "INPUT" && (
            <div className={styles.emptyState}>
              <span className={styles.emptyLabel}>{"//"} CONFIGURE SCENARIO</span>
              <span className={styles.emptyHint}>
                Fill in the scenario and parameters, then click Run Simulation.
              </span>
            </div>
          )}

          {state.status === "RUNNING" && (
            <Pane header="SWARM CANVAS" value={`Round ${state.round}/${state.totalRounds}`}>
              <div className={styles.swarmPlaceholder}>
                <LiveDot pulse />
                <span>Simulation in progress — {state.agents > 0 ? `${state.agents} agents` : ""}</span>
              </div>
            </Pane>
          )}

          {state.status === "REPORT" && (
            <Pane header="REPORT" value="COMPLETE">
              <div className={styles.reportPlaceholder}>
                <span>Report generated successfully. View sections below.</span>
              </div>
            </Pane>
          )}

          {state.status === "ERROR" && (
            <Pane header="ERROR" value="">
              <div className={styles.errorState}>
                <span>{state.errorMessage || "An unknown error occurred."}</span>
                <Button onClick={() => window.location.reload()}>Retry</Button>
              </div>
            </Pane>
          )}
        </div>
      </main>
    </div>
  );
}
