import { useState } from "react";
import { AppChrome } from "./components/AppChrome/AppChrome";
import { MarketingNav } from "./components/AppChrome/MarketingNav";
import { HomePage } from "./pages/HomePage";
import { SimulatorPage } from "./pages/SimulatorPage";
import "./styles/globals.css";

function App() {
  const [tab, setTab] = useState<"home" | "simulate">("home");
  const [scenarioPrefill, setScenarioPrefill] = useState("");

  const handleScenarioSelect = (text: string) => {
    setScenarioPrefill(text);
    setTab("simulate");
  };

  return (
    <div>
      {tab === "home" ? (
        <>
          <MarketingNav />
          <HomePage onScenarioSelect={handleScenarioSelect} />
        </>
      ) : (
        <>
          <AppChrome activeTab="simulate" onTabChange={(t) => { if (t === "home") setTab("home"); }} />
          <SimulatorPage initialScenario={scenarioPrefill} />
        </>
      )}
    </div>
  );
}

export default App;
