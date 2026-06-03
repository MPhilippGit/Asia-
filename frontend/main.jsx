import "vite/modulepreload-polyfill";
import "./scss/app.scss";
import "./scss/components/main.scss";
import { StrictMode, useState } from "react";
import { Sidebar } from "./components/Sidebar.jsx";
import { Board } from "./components/Board.jsx";
import { createRoot } from "react-dom/client";
import { PATHS } from "./globals.js";
import { Dashboard } from "./components/Dashboard.jsx";
import Recordings from "./components/Recordings.jsx";

const root = createRoot(document.getElementById("root"));
root.render(
  <StrictMode>
    <App />
  </StrictMode>,
);

function App() {
  const [graph, setGraph] = useState(PATHS.DASHBOARD);
  return (
    <div className="dash">
      <Sidebar graph={graph} setGraph={setGraph} />
      {graph === "dashboard" ? (
        <Dashboard />
      ) : graph === "recordings" ? (
        <Recordings />
      ) : (
        <Board graph={graph} setGraph={setGraph} />
      )}
    </div>
  );
}
