import { useMemo, useState } from "react";
import { api } from "../api";
import type { ApiError, BacktestRequest, BacktestResponse, Side, SizeMode } from "../types";
import { sideLabel, sizeModeLabel } from "../labels";
import { formatDecimalUsdt, formatPercent } from "../formatters";
import { ErrorBanner } from "./ErrorBanner";
import { SymbolPicker } from "./SymbolPicker";
import { PayoutTimelineChart } from "./PayoutTimelineChart";
import { RateHistogram } from "./RateHistogram";
import { PaymentTable } from "./PaymentTable";

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function toLocalInput(d: Date): string {
  // YYYY-MM-DDTHH:MM (no seconds, no tz)
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
  if (Number.isNaN(d.getTime())) return s;
  return d.toISOString();
}

function isoToLocalInput(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16);
  return toLocalInput(d);
}

function signClass(s: string | null | undefined): string {
  if (s === null || s === undefined || s === "") return "";
  const n = Number(s);
  if (!Number.isFinite(n) || n === 0) return "";
  return n > 0 ? "ok" : "err";
}

export function BacktestPage() {
  const [symbol, setSymbol] = useState("");
  const [side, setSide] = useState<Side>("LONG");
  const [start, setStart] = useState<string>(defaultStart());
  const [end, setEnd] = useState<string>(defaultEnd());
  const [sizeMode, setSizeMode] = useState<SizeMode>("BASE");
  const [size, setSize] = useState<string>("1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [result, setResult] = useState<BacktestResponse | null>(null);

  const startInput = useMemo(() => isoToLocalInput(start), [start]);
  const endInput = useMemo(() => isoToLocalInput(end), [end]);

  function setQuickRange(days: number) {
    const e = new Date();
    const s = new Date();
    s.setDate(s.getDate() - days);
    s.setHours(0, 0, 0, 0);
    setStart(s.toISOString());
    setEnd(e.toISOString());
  }

  async function handleSubmit() {
    if (!symbol || busy) return;
    setBusy(true);
    setError(null);
    const req: BacktestRequest = {
      symbol,
      side,
      start,
      end,
      size_mode: sizeMode,
      size: sizeMode === "RATE_ONLY" ? undefined : size,
    };
    const r = await api.post<BacktestResponse>("/backtest", req);
    if (r.error) {
      setError(r.error);
      setResult(null);
    } else if (r.data) {
      setResult(r.data);
    }
    setBusy(false);
  }

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
      data-testid="page-backtest"
      style={{ display: "grid", gridTemplateColumns: "360px 1fr", gap: 16 }}
    >
      <aside className="card">
        <h3 style={{ marginTop: 0 }}>回测参数</h3>

        <div style={{ marginBottom: 12 }}>
          <label style={{ display: "block", marginBottom: 4 }}>合约</label>
          <SymbolPicker value={symbol} onChange={setSymbol} />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ display: "block", marginBottom: 4 }}>方向</label>
          <select
            value={side}
            onChange={(e) => setSide(e.target.value as Side)}
            style={{ width: "100%" }}
          >
            <option value="LONG">{sideLabel("LONG")}</option>
            <option value="SHORT">{sideLabel("SHORT")}</option>
          </select>
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ display: "block", marginBottom: 4 }}>开始</label>
          <input
            type="datetime-local"
            value={startInput}
            onChange={(e) => setStart(localInputToIso(e.target.value))}
            style={{ width: "100%", boxSizing: "border-box" }}
          />
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ display: "block", marginBottom: 4 }}>结束</label>
          <input
            type="datetime-local"
            value={endInput}
            onChange={(e) => setEnd(localInputToIso(e.target.value))}
            style={{ width: "100%", boxSizing: "border-box" }}
          />
        </div>

        <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap" }}>
          <button type="button" onClick={() => setQuickRange(7)}>7天</button>
          <button type="button" onClick={() => setQuickRange(30)}>30天</button>
          <button type="button" onClick={() => setQuickRange(90)}>90天</button>
          <button type="button" onClick={() => setQuickRange(365)}>365天</button>
        </div>

        <div style={{ marginBottom: 12 }}>
          <label style={{ display: "block", marginBottom: 4 }}>仓位模式</label>
          <select
            data-testid="size-mode"
            value={sizeMode}
            onChange={(e) => setSizeMode(e.target.value as SizeMode)}
            style={{ width: "100%" }}
          >
            <option value="BASE">{sizeModeLabel("BASE")}</option>
            <option value="QUOTE">{sizeModeLabel("QUOTE")}</option>
            <option value="RATE_ONLY">{sizeModeLabel("RATE_ONLY")}</option>
          </select>
        </div>

        {sizeMode !== "RATE_ONLY" && (
          <div style={{ marginBottom: 12 }}>
            <label style={{ display: "block", marginBottom: 4 }}>仓位大小</label>
            <input
              type="text"
              value={size}
              onChange={(e) => setSize(e.target.value)}
              style={{ width: "100%", boxSizing: "border-box" }}
            />
          </div>
        )}

        <button
          type="button"
          className="primary"
          onClick={() => void handleSubmit()}
          disabled={busy || !symbol}
        >
          {busy ? "运行中…" : "跑回测"}
        </button>
      </aside>

      <section>
        <ErrorBanner error={error} onDismiss={() => setError(null)} />

        {result ? (
          <>
            <div className="card" style={{ marginBottom: 16 }}>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(5, 1fr)",
                  gap: 12,
                }}
              >
                <div>
                  <div style={metricLabelStyle}>期数</div>
                  <div style={metricValueStyle}>{result.event_count}</div>
                </div>
                <div>
                  <div style={metricLabelStyle}>累计费率</div>
                  <div
                    style={metricValueStyle}
                    className={signClass(result.cumulative_rate_pct)}
                  >
                    {formatPercent(result.cumulative_rate_pct)}
                  </div>
                </div>
                <div>
                  <div style={metricLabelStyle}>平均费率</div>
                  <div style={metricValueStyle}>
                    {formatPercent(result.avg_rate_pct)}
                  </div>
                </div>
                <div>
                  <div style={metricLabelStyle}>年化</div>
                  <div
                    style={metricValueStyle}
                    className={signClass(result.annualized_pct)}
                  >
                    {formatPercent(result.annualized_pct)}
                  </div>
                </div>
                <div>
                  <div style={metricLabelStyle}>合计（USDT）</div>
                  <div style={metricValueStyle}>
                    {result.total_quote === null
                      ? "—"
                      : formatDecimalUsdt(result.total_quote)}
                  </div>
                </div>
              </div>
            </div>

            <div className="card" style={{ marginBottom: 16 }}>
              <h4 style={{ marginTop: 0 }}>时间线</h4>
              <PayoutTimelineChart payments={result.payments} />
            </div>

            <div className="card" style={{ marginBottom: 16 }}>
              <h4 style={{ marginTop: 0 }}>费率分布</h4>
              <RateHistogram payments={result.payments} />
            </div>

            <PaymentTable payments={result.payments} />
          </>
        ) : (
          !busy && (
            <div style={{ color: "var(--color-muted)" }}>
              填写左侧参数后点击“跑回测”。
            </div>
          )
        )}
      </section>
    </div>
  );
}
