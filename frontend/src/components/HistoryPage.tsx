import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type {
  AccountSummary,
  ApiError,
  HistoryRequest,
} from "../types";
import { taskStatusLabel } from "../labels";
import { formatDecimalUsdt } from "../formatters";
import { useTaskPoll } from "../useTaskPoll";
import { ErrorBanner } from "./ErrorBanner";
import { MonthlyTrendChart } from "./MonthlyTrendChart";
import { SymbolBarChart } from "./SymbolBarChart";
import { HistoryTable } from "./HistoryTable";

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function toLocalInput(d: Date): string {
  return (
    `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}` +
    `T${pad2(d.getHours())}:${pad2(d.getMinutes())}`
  );
}

function defaultEnd(): string {
  return new Date().toISOString();
}

function defaultStart(): string {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  d.setHours(0, 0, 0, 0);
  return d.toISOString();
}

function localInputToIso(s: string): string {
  if (!s) return "";
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return "";
  return d.toISOString();
}

function isoToLocalInput(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16);
  return toLocalInput(d);
}

function rangeDays(startIso: string, endIso: string): number | null {
  if (!startIso || !endIso) return null;
  const s = new Date(startIso).getTime();
  const e = new Date(endIso).getTime();
  if (!Number.isFinite(s) || !Number.isFinite(e) || e < s) return null;
  return (e - s) / 86400000;
}

export function HistoryPage() {
  const [accounts, setAccounts] = useState<AccountSummary[]>([]);
  const [accountName, setAccountName] = useState<string>("");
  const [start, setStart] = useState<string>(defaultStart());
  const [end, setEnd] = useState<string>(defaultEnd());
  const [symbol, setSymbol] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);

  const { status, error: pollError } = useTaskPoll(taskId);

  const mountedRef = useRef(true);
  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // Load accounts list once on mount.
  useEffect(() => {
    void api.get<{ accounts: AccountSummary[] }>("/accounts").then((r) => {
      if (!mountedRef.current) return;
      if (r.error) {
        setError(r.error);
        return;
      }
      const list = r.data?.accounts ?? [];
      setAccounts(list);
      if (list.length > 0) setAccountName((prev) => prev || list[0].name);
    });
  }, []);

  // Surface poll errors via the same banner.
  useEffect(() => {
    if (pollError) setError(pollError);
  }, [pollError]);

  const startInput = useMemo(() => isoToLocalInput(start), [start]);
  const endInput = useMemo(() => isoToLocalInput(end), [end]);
  const days = useMemo(() => rangeDays(start, end), [start, end]);
  const showLongQueryWarn = days !== null && days > 90;

  async function run() {
    if (busy) return;
    if (!accountName || !start || !end) {
      setError({
        code: "validation_error",
        message: "请填写账户和起止时间",
      });
      return;
    }
    setBusy(true);
    setError(null);
    setTaskId(null);
    const req: HistoryRequest = {
      account_name: accountName,
      start,
      end,
    };
    if (symbol.trim()) req.symbol = symbol.trim();
    const r = await api.post<{ task_id: string; status: string }>("/history", req);
    if (!mountedRef.current) return;
    if (r.error) {
      setError(r.error);
      setBusy(false);
      return;
    }
    if (r.data?.task_id) {
      setTaskId(r.data.task_id);
    }
    setBusy(false);
  }

  const isPolling = taskId !== null && status?.status !== "done" && status?.status !== "failed";
  const result = status?.status === "done" ? status.result : undefined;

  const metricLabelStyle: React.CSSProperties = {
    fontSize: 12,
    color: "var(--color-muted)",
  };
  const metricValueStyle: React.CSSProperties = {
    fontSize: 20,
    fontWeight: 600,
    marginTop: 4,
  };

  return (
    <div
      data-testid="page-history"
      style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 16 }}
    >
      <aside className="card">
        <h3 style={{ marginTop: 0 }}>查询历史</h3>

        <div style={{ marginBottom: 12 }}>
          <label htmlFor="history-account" style={{ display: "block", marginBottom: 4 }}>
            账户
          </label>
          <select
            id="history-account"
            value={accountName}
            onChange={(e) => setAccountName(e.target.value)}
            style={{ width: "100%" }}
          >
            {accounts.length === 0 && <option value="">（暂无账户）</option>}
            {accounts.map((a) => (
              <option key={a.name} value={a.name}>
                {a.label || a.name}
              </option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: 12 }}>
          <label htmlFor="history-start" style={{ display: "block", marginBottom: 4 }}>
            开始
          </label>
          <input
            id="history-start"
            type="datetime-local"
            value={startInput}
            onChange={(e) => setStart(localInputToIso(e.target.value))}
            style={{ width: "100%", boxSizing: "border-box" }}
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label htmlFor="history-end" style={{ display: "block", marginBottom: 4 }}>
            结束
          </label>
          <input
            id="history-end"
            type="datetime-local"
            value={endInput}
            onChange={(e) => setEnd(localInputToIso(e.target.value))}
            style={{ width: "100%", boxSizing: "border-box" }}
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label htmlFor="history-symbol" style={{ display: "block", marginBottom: 4 }}>
            合约（可空）
          </label>
          <input
            id="history-symbol"
            type="text"
            value={symbol}
            placeholder="如 BTCUSDT，留空查询全部"
            onChange={(e) => setSymbol(e.target.value)}
            style={{ width: "100%", boxSizing: "border-box" }}
          />
        </div>

        {showLongQueryWarn && (
          <div
            role="alert"
            className="warn-banner"
            style={{
              marginBottom: 12,
              padding: "8px 12px",
              borderRadius: 4,
              fontSize: 13,
              border: "1px solid var(--color-warn)",
            }}
          >
            查询时间较长（&gt;90 天），可能耗时数分钟。
          </div>
        )}

        <button
          type="button"
          className="primary"
          onClick={() => void run()}
          disabled={busy || isPolling}
        >
          {busy || isPolling ? "查询中…" : "查询"}
        </button>
      </aside>

      <section>
        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        {isPolling && status && (
          <div className="card" style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 8 }}>
              状态：{taskStatusLabel(status.status)}
              {status.progress && (
                <span style={{ marginLeft: 12, color: "var(--color-muted)" }}>
                  {status.progress.processed} / {status.progress.total}
                </span>
              )}
            </div>
            {status.progress && status.progress.total > 0 && (
              <div
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={status.progress.total}
                aria-valuenow={status.progress.processed}
                style={{
                  height: 8,
                  background: "var(--color-surface-alt)",
                  borderRadius: 4,
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    width: `${Math.min(
                      100,
                      (status.progress.processed / status.progress.total) * 100,
                    )}%`,
                    height: "100%",
                    background: "var(--color-accent)",
                  }}
                />
              </div>
            )}
          </div>
        )}

        {result ? (
          <>
            <div className="card" style={{ marginBottom: 16 }}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(3, 1fr)",
                  gap: 12,
                }}
              >
                <div>
                  <div style={metricLabelStyle}>合计（USDT）</div>
                  <div
                    style={metricValueStyle}
                    className={`metric-value ${Number(result.total) >= 0 ? "ok" : "err"}`}
                  >
                    {formatDecimalUsdt(result.total)}
                  </div>
                </div>
                <div>
                  <div style={metricLabelStyle}>合约数</div>
                  <div style={metricValueStyle}>
                    {Object.keys(result.by_symbol).length}
                  </div>
                </div>
                <div>
                  <div style={metricLabelStyle}>明细条数</div>
                  <div style={metricValueStyle}>{result.records.length}</div>
                </div>
              </div>
            </div>

            <div className="card" style={{ marginBottom: 16 }}>
              <h4 style={{ marginTop: 0 }}>月度趋势</h4>
              <MonthlyTrendChart byMonth={result.by_month} />
            </div>

            <div className="card" style={{ marginBottom: 16 }}>
              <h4 style={{ marginTop: 0 }}>按合约（前 20）</h4>
              <SymbolBarChart bySymbol={result.by_symbol} />
            </div>

            <HistoryTable records={result.records} />
          </>
        ) : (
          !busy && !isPolling && (
            <div style={{ color: "var(--color-muted)" }}>
              填写左侧参数后点击"查询"。
            </div>
          )
        )}
      </section>
    </div>
  );
}
