import { useState, useEffect } from "react";
import { BrowserRouter, Routes, Route, useNavigate, useParams } from "react-router-dom";
import { AppChrome } from "./components/AppChrome/AppChrome";
import { MarketingNav } from "./components/AppChrome/MarketingNav";
import { HomePage } from "./pages/HomePage";
import { SimulatorPage } from "./pages/SimulatorPage";
import { ReportPage } from "./pages/ReportPage";
import "./styles/globals.css";

function HomeShell() {
  const navigate = useNavigate();

  const handleScenarioSelect = (text: string) => {
    navigate(text ? `/simulate/new?scenario=${encodeURIComponent(text)}` : "/simulate/new");
  };

  return (
    <>
      <MarketingNav />
      <HomePage onScenarioSelect={handleScenarioSelect} />
    </>
  );
}

function SimulatorShell() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = !id || id === "new";

  return (
    <>
      <AppChrome activeTab="simulate" onTabChange={(t) => { if (t === "home") navigate("/"); }} />
      <SimulatorPage
        initialScenario={isNew ? new URLSearchParams(window.location.search).get("scenario") ?? "" : ""}
        simId={isNew ? undefined : id}
      />
    </>
  );
}

function ReportShell() {
  const { id } = useParams<{ id: string }>();
  const [sections, setSections] = useState<Record<string, string> | null>(null);
  const [scenario, setScenario] = useState("");
  const [status, setStatus] = useState<"loading" | "in_progress" | "ready" | "error">("loading");

  useEffect(() => {
    if (!id) return;
    fetch(`/report/${id}`)
      .then((r) => {
        if (r.status === 202) {
          setStatus("in_progress");
          return null;
        }
        return r.json();
      })
      .then((data) => {
        if (!data) return;
        if (data.sections) {
          setSections(data.sections);
          setScenario(data.scenario ?? "");
          setStatus("ready");
        }
      })
      .catch(() => setStatus("error"));
  }, [id]);

  if (!id) return <div style={{ padding: 40, color: "var(--dim)" }}>No report ID specified.</div>;
  if (status === "loading") return <div style={{ padding: 40, color: "var(--dim)" }}>Loading report...</div>;
  if (status === "in_progress") return <div style={{ padding: 40, color: "var(--accent)" }}>Report generation in progress — check back soon.</div>;
  if (status === "error" || !sections) return <div style={{ padding: 40, color: "var(--dim)" }}>Report not available.</div>;

  return <ReportPage simId={id} scenario={scenario || "Simulation"} sections={sections} />;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomeShell />} />
        <Route path="/simulate/:id" element={<SimulatorShell />} />
        <Route path="/report/:id" element={<ReportShell />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
