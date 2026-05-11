import styles from "./SentimentChart.module.css";

interface SentimentRound {
  round: number;
  positive_pct: number;
  negative_pct: number;
  neutral_pct: number;
}

interface SentimentChartProps {
  data: SentimentRound[];
  width?: number;
  height?: number;
}

export function SentimentChart({ data, width = 400, height = 160 }: SentimentChartProps) {
  const barWidth = Math.max(8, Math.min(24, (width - 40) / Math.max(data.length, 1) - 4));

  const readVar = (name: string): string =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  const posColor = readVar("--pos") || "#4ade80";
  const negColor = readVar("--neg") || "#f87171";
  const neuColor = readVar("--ink2") || "#9a9a9a";

  return (
    <svg
      className={styles.chart}
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-label="Sentiment over rounds chart"
    >
      <text x={8} y={12} fill={readVar("--dim")} fontSize="9" fontFamily="JetBrains Mono">
        SENTIMENT
      </text>

      {data.map((d, i) => {
        const x = 20 + i * (barWidth + 4);
        const scale = (height - 30) / 100;
        const posH = d.positive_pct * scale;
        const negH = d.negative_pct * scale;
        const neuH = d.neutral_pct * scale;
        const yBase = height - 10;

        return (
          <g key={d.round} className={styles.barGroup}>
            <rect x={x} y={yBase - posH - negH - neuH} width={barWidth} height={posH} fill={posColor} />
            <rect x={x} y={yBase - negH - neuH} width={barWidth} height={negH} fill={negColor} />
            <rect x={x} y={yBase - neuH} width={barWidth} height={neuH} fill={neuColor} />
            <text
              x={x + barWidth / 2}
              y={height - 2}
              fill={readVar("--dim")}
              fontSize="7"
              fontFamily="JetBrains Mono"
              textAnchor="middle"
            >
              {d.round}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
