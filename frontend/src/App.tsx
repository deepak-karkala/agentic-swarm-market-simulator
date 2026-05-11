import { useState } from "react";
import { AppChrome } from "./components/AppChrome/AppChrome";
import { HomePage } from "./pages/HomePage";
import { SimulatorPage } from "./pages/SimulatorPage";
import "./styles/globals.css";

function App() {
  const [tab, setTab] = useState<"home" | "simulate">("simulate");

  return (
    <div>
      <AppChrome activeTab={tab} onTabChange={setTab} />
      {tab === "home" ? <HomePage /> : <SimulatorPage />}
    </div>
  );
}

export default App;
