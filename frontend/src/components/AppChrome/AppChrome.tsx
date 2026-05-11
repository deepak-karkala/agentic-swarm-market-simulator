import styles from "./AppChrome.module.css";

interface AppChromeProps {
  activeTab?: "home" | "simulate";
  onTabChange?: (tab: "home" | "simulate") => void;
}

export function AppChrome({ activeTab = "simulate", onTabChange }: AppChromeProps) {
  return (
    <header className={styles.chrome}>
      <span className={styles.logo}>AGENTIC MARKET SIM</span>
      <nav className={styles.tabs}>
        <button
          type="button"
          className={`${styles.tab} ${activeTab === "home" ? styles.tabActive : ""}`}
          onClick={() => onTabChange?.("home")}
        >
          01 HOME
        </button>
        <button
          type="button"
          className={`${styles.tab} ${activeTab === "simulate" ? styles.tabActive : ""}`}
          onClick={() => onTabChange?.("simulate")}
        >
          02 SIMULATE
        </button>
      </nav>
    </header>
  );
}
