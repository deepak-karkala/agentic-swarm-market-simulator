import styles from "./Button.module.css";

interface ButtonProps {
  variant?: "primary" | "secondary";
  onClick?: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}

export function Button({ variant = "secondary", onClick, disabled, children }: ButtonProps) {
  const cls = variant === "primary" ? `${styles.btn} ${styles.primary}` : styles.btn;
  return (
    <button type="button" className={cls} onClick={onClick} disabled={disabled}>
      {children}
    </button>
  );
}
