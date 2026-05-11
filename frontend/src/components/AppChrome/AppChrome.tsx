import styles from "./AppChrome.module.css";

interface AppChromeProps {
  activeTab?: "home" | "simulate";
}

export function AppChrome({ activeTab = "simulate" }: AppChromeProps) {
  return (
    <header className={styles.chrome}>
      <span className={styles.logo}>AGENTIC MARKET SIM</span>
      <nav className={styles.tabs}>
        <button
          className={`${styles.tab} ${activeTab === "home" ? styles.tabActive : ""}`}
          data-tab="home"
        >
          01 HOME
        </button>
        <button
          className={`${styles.tab} ${activeTab === "simulate" ? styles.tabActive : ""}`}
          data-tab="simulate"
        >
          02 SIMULATE
        </button>
      </nav>
    </header>
  );
}
