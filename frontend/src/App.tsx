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
  if (!id) return <div style={{ padding: 40, color: "var(--dim)" }}>No report ID specified.</div>;

  return <ReportPage simId={id} scenario="Simulation" sections={{}} />;
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
