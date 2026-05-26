import { useEffect, useState } from "react";
import { csrfStore } from "./csrfStore";
import { ErrorBanner } from "./components/ErrorBanner";
import { BacktestPage } from "./components/BacktestPage";
import { HistoryPage } from "./components/HistoryPage";
import { AccountsPage } from "./components/AccountsPage";
import type { ApiError } from "./types";

type Tab = "backtest" | "history" | "accounts";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "backtest", label: "回测" },
  { id: "history", label: "历史" },
  { id: "accounts", label: "账户" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("backtest");
  const [bootError, setBootError] = useState<ApiError | null>(null);

  useEffect(() => {
    csrfStore.getToken().catch(() => {
      setBootError({ code: "csrf_mismatch", message: "无法初始化安全令牌，请刷新页面" });
    });
  }, []);

  return (
    <div className="app-shell">
      <nav className="tab-bar">
        {TABS.map(t => (
          <button
            key={t.id}
            className={tab === t.id ? "active" : ""}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>
      <ErrorBanner error={bootError} onDismiss={() => setBootError(null)} />
      <main>
        {tab === "backtest" && <BacktestPage />}
        {tab === "history" && <HistoryPage />}
        {tab === "accounts" && <AccountsPage />}
      </main>
    </div>
  );
}
