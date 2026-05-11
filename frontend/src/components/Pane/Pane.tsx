import styles from "./Pane.module.css";

interface PaneProps {
  header?: string;
  value?: string;
  children: React.ReactNode;
}

export function Pane({ header, value, children }: PaneProps) {
  return (
    <div className={styles.pane}>
      {header && (
        <div className={styles.header}>
          <span>{header}</span>
          {value && <span className={styles.value}>{value}</span>}
        </div>
      )}
      <div className={styles.body}>{children}</div>
    </div>
  );
}
