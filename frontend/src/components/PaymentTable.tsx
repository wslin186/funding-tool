import { useMemo, useState } from "react";
import type { FundingPayment } from "../types";
import { csvEscape, formatDecimalUsdt, formatPercent, formatTimestamp } from "../formatters";

interface Props {
  payments: FundingPayment[];
}

type SortKey = "timestamp" | "rate" | "payment_quote";
type SortDir = "asc" | "desc";

function signColor(s: string): string | undefined {
  const n = Number(s);
  if (!Number.isFinite(n) || n === 0) return undefined;
  return n > 0 ? "var(--color-ok)" : "var(--color-err)";
}

function compareNum(a: string, b: string): number {
  const na = Number(a);
  const nb = Number(b);
  const va = Number.isFinite(na) ? na : 0;
  const vb = Number.isFinite(nb) ? nb : 0;
  return va - vb;
}

export function PaymentTable({ payments }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("timestamp");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const sorted = useMemo(() => {
    const arr = [...payments];
    arr.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "timestamp") {
        cmp = a.timestamp.localeCompare(b.timestamp);
      } else if (sortKey === "rate") {
        cmp = compareNum(a.rate, b.rate);
      } else {
        cmp = compareNum(a.payment_quote, b.payment_quote);
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [payments, sortKey, sortDir]);

  function toggleSort(k: SortKey) {
    if (k === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(k);
      setSortDir("asc");
    }
  }

  function arrow(k: SortKey): string {
    if (k !== sortKey) return "";
    return sortDir === "asc" ? " ▲" : " ▼";
  }

  function exportCsv() {
    const header = ["时间", "费率", "标记价", "持仓", "名义", "收益"];
    const rows = sorted.map((p) => [
      formatTimestamp(p.timestamp),
      p.rate,
      p.mark_price,
      p.quantity_base,
      p.notional_quote,
      p.payment_quote,
    ]);
    const csv = [header, ...rows]
      .map((r) => r.map((c) => csvEscape(String(c))).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "backtest.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  const thStyle: React.CSSProperties = {
    cursor: "pointer",
    textAlign: "left",
    padding: "8px 12px",
    borderBottom: "1px solid var(--color-border, #ddd)",
    position: "sticky",
    top: 0,
    background: "var(--color-bg, #fff)",
  };
  const tdStyle: React.CSSProperties = {
    padding: "6px 12px",
    borderBottom: "1px solid var(--color-border, #eee)",
  };

  return (
    <div className="card">
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 8,
        }}
      >
        <strong>支付明细</strong>
        <button type="button" onClick={exportCsv}>导出 CSV</button>
      </div>
      <div style={{ maxHeight: 360, overflowY: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={thStyle} onClick={() => toggleSort("timestamp")}>
                时间{arrow("timestamp")}
              </th>
              <th style={thStyle} onClick={() => toggleSort("rate")}>
                费率{arrow("rate")}
              </th>
              <th style={{ ...thStyle, cursor: "default" }}>标记价</th>
              <th style={{ ...thStyle, cursor: "default" }}>持仓</th>
              <th style={{ ...thStyle, cursor: "default" }}>名义</th>
              <th style={thStyle} onClick={() => toggleSort("payment_quote")}>
                收益{arrow("payment_quote")}
              </th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((p) => (
              <tr key={`${p.timestamp}-${p.payment_quote}`}>
                <td style={tdStyle}>{formatTimestamp(p.timestamp)}</td>
                <td style={{ ...tdStyle, color: signColor(p.rate) }}>{formatPercent(p.rate)}</td>
                <td style={tdStyle}>{formatDecimalUsdt(p.mark_price)}</td>
                <td style={tdStyle}>{p.quantity_base}</td>
                <td style={tdStyle}>{formatDecimalUsdt(p.notional_quote)}</td>
                <td style={{ ...tdStyle, color: signColor(p.payment_quote) }}>
                  {formatDecimalUsdt(p.payment_quote)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
