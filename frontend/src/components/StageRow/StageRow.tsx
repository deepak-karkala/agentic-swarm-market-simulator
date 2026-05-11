import styles from "./StageRow.module.css";

type StageStatus = "done" | "run" | "idle";

interface StageRowProps {
  status: StageStatus;
  label: string;
}

const ICONS: Record<StageStatus, string> = {
  done: "\u2713",
  run: "\u25B8",
  idle: "\u00B7",
};

export function StageRow({ status, label }: StageRowProps) {
  const prefixCls = status === "run" ? `${styles.prefix} ${styles.blink}` : styles.prefix;
  return (
    <div className={`${styles.row} ${styles[status]}`}>
      <span className={prefixCls}>{ICONS[status]}</span>
      <span>{label}</span>
    </div>
  );
}
