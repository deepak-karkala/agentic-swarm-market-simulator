import { useState } from "react";
import { AppChrome } from "./components/AppChrome/AppChrome";
import { HomePage } from "./pages/HomePage";
import { SimulatorPage } from "./pages/SimulatorPage";
import "./styles/globals.css";

function App() {
  const [tab, setTab] = useState<"home" | "simulate">("home");
  const [scenarioPrefill, setScenarioPrefill] = useState("");

  const handleTabChange = (newTab: "home" | "simulate") => {
    setTab(newTab);
    if (newTab === "simulate") {
      setScenarioPrefill(""); // clear prefill on plain tab switch
    }
  };

  const handleScenarioSelect = (text: string) => {
    setScenarioPrefill(text);
    setTab("simulate");
  };

  return (
    <div>
      <AppChrome activeTab={tab} onTabChange={handleTabChange} />
      {tab === "home" ? (
        <HomePage onScenarioSelect={handleScenarioSelect} />
      ) : (
        <SimulatorPage initialScenario={scenarioPrefill} />
      )}
    </div>
  );
}

export default App;
