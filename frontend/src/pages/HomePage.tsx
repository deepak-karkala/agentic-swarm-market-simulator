import { Button } from "../components/Button/Button";
import styles from "./HomePage.module.css";

interface HomePageProps {
  onScenarioSelect?: (text: string) => void;
}

const SCENARIOS = [
  "Apple launches an electric vehicle at $35,000",
  "TikTok ban goes into effect in the US",
  "FDA approves Ozempic for over-the-counter use",
];

export function HomePage({ onScenarioSelect }: HomePageProps) {
  const handleNavigate = () => onScenarioSelect?.("");
  const handleScenario = (text: string) => onScenarioSelect?.(text);

  return (
    <div className={styles.page}>
      {/* Hero */}
      <section className={styles.hero}>
        <div className={styles.tagline}>{"//"} FLIGHT SIMULATOR FOR MARKET DYNAMICS</div>
        <h1 className={styles.headline}>
          Run the market reaction before you commit the budget.
        </h1>
        <p className={styles.subhead}>
          200 culturally-calibrated AI agents simulate your scenario across social media,
          boardrooms, and analyst desks — producing a business impact report with
          McKinsey-level depth in minutes.
        </p>
        <div className={styles.ctaGroup}>
          <Button variant="primary" onClick={handleNavigate}>
            {"\u25B6"} RUN YOUR SCENARIO
          </Button>
        </div>
      </section>

      {/* How it works */}
      <section className={styles.section}>
        <div className={styles.sectionNum}>01</div>
        <div className={styles.sectionContent}>
          <h2 className={styles.sectionHeading}>How It Works</h2>
          <p className={styles.sectionText}>
            A 5-stage pipeline transforms your scenario into actionable intelligence.
          </p>
          <div className={styles.pipeline}>
            {[
              { num: "0", name: "Seed", desc: "Gathers competitive intel, regulations, KOLs, macro data" },
              { num: "1", name: "Graph", desc: "Builds a knowledge graph from enriched context" },
              { num: "2", name: "Agents", desc: "Generates 200 geo-calibrated agent personas" },
              { num: "3", name: "Simulate", desc: "Runs 3 simulation tracks concurrently" },
              { num: "4", name: "Report", desc: "Synthesizes a 10-section business report" },
            ].map((s) => (
              <div key={s.num} className={styles.pipelineStep}>
                <div className={styles.stepNum}>{s.num}</div>
                <div className={styles.stepName}>{s.name}</div>
                <div className={styles.stepDesc}>{s.desc}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* 3-track architecture */}
      <section className={styles.section}>
        <div className={styles.sectionNum}>02</div>
        <div className={styles.sectionContent}>
          <h2 className={styles.sectionHeading}>3-Track Parallel Simulation</h2>
          <div className={styles.tracks}>
            <div className={styles.track}>
              <div className={styles.trackLabel}>Track 1</div>
              <div className={styles.trackText}>
                Public narrative — 200 agents on Twitter simulate social media cascade,
                sentiment shifts, and information spread across 10 rounds.
              </div>
            </div>
            <div className={styles.track}>
              <div className={styles.trackLabel}>Track 2</div>
              <div className={styles.trackText}>
                Boardroom — C-suite agents deliberate competitive responses using
                structured strategy frameworks and market intelligence.
              </div>
            </div>
            <div className={styles.track}>
              <div className={styles.trackLabel}>Track 3</div>
              <div className={styles.trackText}>
                Analyst desk — sell-side analysts produce earnings revisions,
                price target changes, and investment thesis updates.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Calibration */}
      <section className={styles.section}>
        <div className={styles.sectionNum}>03</div>
        <div className={styles.sectionContent}>
          <h2 className={styles.sectionHeading}>Gets Smarter With Use</h2>
          <p className={styles.sectionText}>
            Every simulation feeds a collective intelligence engine. After multiple
            simulations, the platform compares predictions to real outcomes and surfaces
            calibration scores for similar past scenarios.
          </p>
          <div style={{ display: "flex", gap: 40, marginTop: 24 }}>
            <div>
              <div className={styles.bigNum}>200</div>
              <div className={styles.bigNumLabel}>Agents per simulation</div>
            </div>
            <div>
              <div className={styles.bigNum}>10</div>
              <div className={styles.bigNumLabel}>Report sections</div>
            </div>
            <div>
              <div className={styles.bigNum}>~12m</div>
              <div className={styles.bigNumLabel}>Typical run time</div>
            </div>
          </div>
        </div>
      </section>

      {/* Try scenarios */}
      <section className={styles.section}>
        <div className={styles.sectionNum}>04</div>
        <div className={styles.sectionContent}>
          <h2 className={styles.sectionHeading}>Try These Scenarios</h2>
          <div className={styles.tryScenarios}>
            {SCENARIOS.map((s) => (
              <button
                key={s}
                type="button"
                className={styles.tryBtn}
                onClick={() => handleScenario(s)}
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Bottom CTA */}
      <section className={styles.ctaBottom}>
        <h2 className={styles.ctaHeadline}>Ready to run your first simulation?</h2>
        <Button variant="primary" onClick={handleNavigate}>
          {"\u25B6"} RUN YOUR SCENARIO
        </Button>
        <div className={styles.ctaMeta}>
          Typical run: 12 minutes · ~$4 per simulation · 10-section report
        </div>
      </section>
    </div>
  );
}
