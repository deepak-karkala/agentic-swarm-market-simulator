import { useState, useCallback } from "react";
import { Chip } from "../components/Chip/Chip";
import { Button } from "../components/Button/Button";
import styles from "./ReportPage.module.css";

const SECTION_META = [
  { key: "executive_summary", num: "01", title: "Executive Summary" },
  { key: "public_narrative", num: "02", title: "Public Narrative" },
  { key: "competitive_response", num: "03", title: "Competitive Response" },
  { key: "financial_impact", num: "04", title: "Financial Impact" },
  { key: "consumer_adoption", num: "05", title: "Consumer Adoption" },
  { key: "strategic_recommendations", num: "06", title: "Strategic Recs" },
  { key: "competitive_landscape", num: "07", title: "Competitive Landscape" },
  { key: "regulatory", num: "08", title: "Regulatory" },
  { key: "kol_impact", num: "09", title: "KOL Impact" },
  { key: "methodology", num: "10", title: "Methodology" },
];

interface ReportProps {
  simId: string;
  scenario: string;
  sections: Record<string, string>;
  horizon?: string;
  calibration?: string;
}

export function ReportPage({ simId, scenario, sections, horizon, calibration }: ReportProps) {
  const [shared, setShared] = useState(false);

  const handleShare = useCallback(() => {
    const url = `${window.location.origin}/report/${simId}`;
    const copied = () => {
      setShared(true);
      setTimeout(() => setShared(false), 1500);
    };
    navigator.clipboard.writeText(url).then(
      copied,
      () => {
        window.prompt("Copy this URL:", url);
        copied();
      },
    );
  }, [simId]);

  const handlePdf = useCallback(() => {
    window.print();
  }, []);

  if (!sections || Object.keys(sections).length === 0) {
    return (
      <div className={styles.page}>
        <div className={styles.emptyReport}>
          <span>{"//"} NO REPORT DATA</span>
        </div>
      </div>
    );
  }

  const exec = sections["executive_summary"] ?? "";

  return (
    <div className={styles.page}>
      <nav className={styles.toc}>
        <span className={styles.tocHeader}>CONTENTS</span>
        {SECTION_META.map((s) => (
          <a
            key={s.key}
            className={styles.tocItem}
            href={`#section-${s.key}`}
          >
            {s.num} {s.title}
          </a>
        ))}
        <div className={styles.tocMeta}>
          <div>SIM: {simId}</div>
          <div>Sections: {Object.keys(sections).length}</div>
        </div>
      </nav>

      <main className={styles.content}>
        <div className={styles.topBar}>
          <div className={styles.topBarLeft}>
            <Chip variant="accent">REPORT</Chip>
            <span className={styles.scenarioName}>{scenario.slice(0, 60)}</span>
          </div>
          <div className={styles.topBarRight}>
            {shared ? (
              <span className={styles.shared}>COPIED {"\u2713"}</span>
            ) : (
              <Button onClick={handleShare}>SHARE</Button>
            )}
            <Button onClick={handlePdf}>PDF</Button>
          </div>
        </div>

        <div className={styles.verdictCards}>
          <div className={styles.verdictCard}>
            <div className={styles.verdictValue}>
              {exec.includes("BULLISH") ? "BULLISH" : exec.includes("BEARISH") ? "BEARISH" : "NEUTRAL"}
            </div>
            <div className={styles.verdictLabel}>VERDICT</div>
            <div className={styles.verdictNote}>Based on simulation data</div>
          </div>
          <div className={styles.verdictCard}>
            <div className={styles.verdictValue}>{horizon || "--"}</div>
            <div className={styles.verdictLabel}>HORIZON</div>
            <div className={styles.verdictNote}>{horizon ? "Expected impact timeline" : "Not available"}</div>
          </div>
          <div className={styles.verdictCard}>
            <div className={styles.verdictValue}>{calibration || "--"}</div>
            <div className={styles.verdictLabel}>CALIBRATION</div>
            <div className={styles.verdictNote}>{calibration || "No prior sims"}</div>
          </div>
        </div>

        {SECTION_META.map((s) => (
          <div key={s.key} id={`section-${s.key}`} className={styles.section}>
            <div className={styles.sectionLabel}>
              SECTION {s.num} / 10 {"\u00B7"} {s.title.toUpperCase()}
            </div>
            <div className={styles.sectionBody}>
              {sections[s.key] || "[Section]: No data available for this section."}
            </div>
          </div>
        ))}
      </main>
    </div>
  );
}
