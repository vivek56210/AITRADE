import { useEffect, useState } from "react";
import { api } from "./api";
import { ControlBar } from "./components/ControlBar";
import { usePoll } from "./hooks";
import { BacktestPage } from "./pages/Backtest";
import { DashboardPage } from "./pages/Dashboard";
import { MarketPage } from "./pages/Market";
import { MonitorPage } from "./pages/Monitor";
import { SettingsPage } from "./pages/Settings";
import { SetupsPage } from "./pages/Setups";
import { SignalsPage } from "./pages/Signals";
import type { Status } from "./types";

const PAGES = [
  { id: "dashboard", label: "Dashboard", icon: "◧" },
  { id: "market", label: "Market", icon: "⌁" },
  { id: "setups", label: "Setups", icon: "☰" },
  { id: "signals", label: "Signals", icon: "◉" },
  { id: "backtest", label: "Backtest", icon: "↗" },
  { id: "monitor", label: "Monitor", icon: "⚙" },
  { id: "settings", label: "Settings", icon: "✎" },
] as const;

type PageId = (typeof PAGES)[number]["id"];

function currentPage(): PageId {
  const id = window.location.hash.replace(/^#\/?/, "");
  return (PAGES.find((p) => p.id === id)?.id ?? "dashboard") as PageId;
}

export interface PageProps {
  status: Status | null;
  refreshStatus: () => void;
}

export function App() {
  const [page, setPage] = useState<PageId>(currentPage);
  const { data: status, error, refresh } = usePoll(api.status, 1000);

  useEffect(() => {
    const onHash = () => setPage(currentPage());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const props: PageProps = { status, refreshStatus: () => void refresh() };

  return (
    <div className="layout">
      <nav className="sidebar" aria-label="Console sections">
        <div className="brand">
          ATIS <span>console</span>
        </div>
        {PAGES.map((p) => (
          <a key={p.id} href={`#/${p.id}`} className={page === p.id ? "active" : ""}>
            <span className="nav-icon" aria-hidden>{p.icon}</span>
            {p.label}
            {p.id === "monitor" && status && (status.jobs_running > 0 || status.state === "error") && (
              <span className={`nav-dot ${status.state === "error" ? "bad" : ""}`} />
            )}
          </a>
        ))}
        <div className="sidebar-foot">
          Recommendation mode
          <br />
          no orders are placed
        </div>
      </nav>
      <div className="main">
        <ControlBar status={status} onChange={() => void refresh()} />
        {error && <div className="alert bad">Console API unreachable: {error}</div>}
        {status?.state === "error" && status.last_error && <div className="alert bad">Runtime error: {status.last_error}</div>}
        {status?.pending_restart && (
          <div className="alert warn">
            Settings changed since the data was loaded. Press <strong>Reset</strong> to apply them.
          </div>
        )}
        <main className="content">
          {page === "dashboard" && <DashboardPage {...props} />}
          {page === "market" && <MarketPage {...props} />}
          {page === "setups" && <SetupsPage {...props} />}
          {page === "signals" && <SignalsPage {...props} />}
          {page === "backtest" && <BacktestPage {...props} />}
          {page === "monitor" && <MonitorPage {...props} />}
          {page === "settings" && <SettingsPage {...props} />}
        </main>
      </div>
    </div>
  );
}
