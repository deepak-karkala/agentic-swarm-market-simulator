import styles from "./LiveDot.module.css";

interface LiveDotProps {
  pulse?: boolean;
}

export function LiveDot({ pulse = true }: LiveDotProps) {
  const cls = pulse ? `${styles.dot} ${styles.pulse}` : styles.dot;
  return <span className={cls} aria-hidden="true" />;
}
