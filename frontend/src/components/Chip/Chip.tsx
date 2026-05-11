import styles from "./Chip.module.css";

interface ChipProps {
  variant?: "default" | "accent" | "positive" | "negative";
  children: React.ReactNode;
}

export function Chip({ variant = "default", children }: ChipProps) {
  const variants: Record<string, string> = {
    accent: styles.accent,
    positive: styles.positive,
    negative: styles.negative,
  };
  const cls = `${styles.chip} ${variants[variant] ?? ""}`.trim();
  return <span className={cls}>{children}</span>;
}
