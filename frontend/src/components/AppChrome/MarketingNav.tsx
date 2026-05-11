import styles from "./MarketingNav.module.css";

export function MarketingNav() {
  return (
    <header className={styles.chrome}>
      <span className={styles.logo}>AGENTIC MARKET SIM</span>
      <nav className={styles.links}>
        <button type="button" className={styles.link}>PRODUCT</button>
        <button type="button" className={styles.link}>METHOD</button>
        <button type="button" className={styles.link}>PRICING</button>
        <button type="button" className={styles.link}>DOCS</button>
      </nav>
      <button type="button" className={styles.ctaPill}>SIGN UP</button>
    </header>
  );
}
