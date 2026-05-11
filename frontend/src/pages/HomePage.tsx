import { Pane } from "../components/Pane/Pane";
import { Button } from "../components/Button/Button";

export function HomePage() {
  return (
    <div style={{ padding: 40, maxWidth: 1680, margin: "0 auto" }}>
      <h1 style={{ fontFamily: "Inter, sans-serif", fontSize: 18, marginBottom: 16 }}>
        Agentic Market Simulator
      </h1>
      <Pane header="PRODUCT" value="v1">
        <div style={{ maxWidth: 600 }}>
          <p style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 10, color: "var(--ink2)", marginBottom: 16 }}>
            A flight simulator for market dynamics. Type a scenario, and in minutes
            200 culturally-calibrated AI agents simulate how it propagates through
            social media, boardrooms, and analyst desks — producing a business
            impact report with McKinsey-level depth.
          </p>
          <Button variant="primary">{"\u25B6"} JOIN WAITLIST</Button>
        </div>
      </Pane>
    </div>
  );
}
