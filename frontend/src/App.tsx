import "./styles/globals.css";
import { useState } from "react";
import { AppChrome } from "./components/AppChrome/AppChrome";
import { Pane } from "./components/Pane/Pane";
import { Button } from "./components/Button/Button";
import { Chip } from "./components/Chip/Chip";
import { LiveDot } from "./components/LiveDot/LiveDot";
import { ProgressBar } from "./components/ProgressBar/ProgressBar";
import { StageRow } from "./components/StageRow/StageRow";
import styles from "./App.module.css";

function App() {
  const [tab, setTab] = useState<"home" | "simulate">("simulate");

  return (
    <div>
      <AppChrome activeTab={tab} onTabChange={setTab} />
      <main className={styles.main}>
        <h1 style={{ fontFamily: "Inter, sans-serif", fontSize: 18, marginBottom: 16 }}>
          Agentic Market Simulator
        </h1>

        <Pane header="COMPONENT GALLERY" value="v1">
          <div style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
            <Button variant="primary">Run Simulation</Button>
            <Button>Cancel</Button>
            <LiveDot pulse />
            <Chip variant="accent">LIVE</Chip>
            <Chip variant="positive">COMPLETE</Chip>
            <Chip variant="negative">FAILED</Chip>
            <Chip>DEFAULT</Chip>
          </div>
          <div style={{ marginTop: 16 }}>
            <ProgressBar value={65} />
          </div>
          <div style={{ marginTop: 16 }}>
            <StageRow status="done" label="0·Seed — Reality Seeding" />
            <StageRow status="run" label="1·Graph — Building knowledge graph" />
            <StageRow status="idle" label="2·Agents — Creating personas" />
            <StageRow status="idle" label="3·Simulate — Running tracks" />
            <StageRow status="idle" label="4·Report — Synthesizing" />
          </div>
        </Pane>
      </main>
    </div>
  );
}

export default App;
