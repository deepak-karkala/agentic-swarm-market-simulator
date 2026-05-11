import styles from "./TickerTape.module.css";

interface TickerEvent {
  round: number;
  agentGroup: string;
  content: string;
}

interface TickerTapeProps {
  events: TickerEvent[];
}

export function TickerTape({ events }: TickerTapeProps) {
  if (events.length === 0) {
    return (
      <div className={styles.tape}>
        <span className={styles.track} style={{ animation: "none", padding: "0 12px" }}>
          No events yet — waiting for simulation data...
        </span>
      </div>
    );
  }

  const tapeContent = events
    .map((e) => `[R${e.round}] [${e.agentGroup.toUpperCase()}] ${e.content.slice(0, 80)}`)
    .join("  \u00B7  ");

  return (
    <div className={styles.tape} aria-live="off">
      <div className={styles.track}>
        {tapeContent}  \u00B7  {tapeContent}
      </div>
    </div>
  );
}
