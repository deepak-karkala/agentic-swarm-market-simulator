import styles from "./MarketingNav.module.css";

export function MarketingNav() {
  const scrollTo = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <header className={styles.chrome}>
      <span className={styles.logo}>AGENTIC MARKET SIM</span>
      <nav className={styles.links}>
        <button type="button" className={styles.link} onClick={() => scrollTo("section-how")}>PRODUCT</button>
        <button type="button" className={styles.link} onClick={() => scrollTo("section-method")}>METHOD</button>
        <button type="button" className={styles.link} onClick={() => scrollTo("section-calibration")}>PRICING</button>
        <button type="button" className={styles.link} onClick={() => scrollTo("section-samples")}>DOCS</button>
      </nav>
      <button type="button" className={styles.ctaPill} onClick={() => scrollTo("section-waitlist")}>SIGN UP</button>
    </header>
  );
}
