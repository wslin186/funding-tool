import { useMemo, useState } from "react";
import type { IncomeRecord } from "../types";
import { csvEscape, formatDecimalUsdt, formatTimestamp } from "../formatters";
import { COLOR_BORDER, COLOR_ERR, COLOR_MUTED, COLOR_OK } from "../themeColors";

interface Props {
  records: IncomeRecord[];
}

type SortKey = "timestamp" | "symbol" | "amount_usdt";
type SortDir = "asc" | "desc";

function compareNum(a: string, b: string): number {
  const na = Number(a);
  const nb = Number(b);
  const va = Number.isFinite(na) ? na : 0;
  const vb = Number.isFinite(nb) ? nb : 0;
  return va - vb;
}

function signColor(s: string): string | undefined {
  const n = Number(s);
  if (!Number.isFinite(n) || n === 0) return undefined;
  return n > 0 ? COLOR_OK : COLOR_ERR;
}

export function HistoryTable({ records }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("timestamp");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const sorted = useMemo(() => {
    const arr = [...records];
    arr.sort((a, b) => {
      let cmp = 0;
      if (sortKey === "timestamp") cmp = a.timestamp.localeCompare(b.timestamp);
      else if (sortKey === "symbol") cmp = a.symbol.localeCompare(b.symbol);
      else cmp = compareNum(a.amount_usdt, b.amount_usdt);
      return sortDir === "asc" ? cmp : -cmp;
    });
    return arr;
  }, [records, sortKey, sortDir]);

  function toggleSort(k: SortKey) {
    if (k === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortKey(k);
      setSortDir("asc");
    }
  }

  function arrow(k: SortKey): string {
    if (k !== sortKey) return "";
    return sortDir === "asc" ? " ▲" : " ▼";
  }

  function exportCsv() {
    const header = ["时间", "合约", "金额（USDT）", "交易 ID"];
    const rows = sorted.map((r) => [
      formatTimestamp(r.timestamp),
      r.symbol,
      r.amount_usdt,
      r.tran_id,
    ]);
    const csv = [header, ...rows]
      .map((r) => r.map((c) => csvEscape(String(c))).join(","))
      .join("\n");
    // Prepend UTF-8 BOM so Excel on Windows decodes Chinese correctly.
    const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "history.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  const thStyle: React.CSSProperties = {
    cursor: "pointer",
    textAlign: "left",
    padding: "8px 12px",
    borderBottom: `1px solid ${COLOR_BORDER}`,
    position: "sticky",
    top: 0,
    background: "var(--color-surface, #fff)",
  };
  const tdStyle: React.CSSProperties = {
    padding: "6px 12px",
    borderBottom: `1px solid ${COLOR_BORDER}`,
  };

  function sortableTh(k: SortKey, label: string) {
    const active = sortKey === k;
    const ariaSort: "ascending" | "descending" | "none" = active
      ? sortDir === "asc"
        ? "ascending"
        : "descending"
      : "none";
    return (
      <th
        style={thStyle}
        role="button"
        tabIndex={0}
        aria-sort={ariaSort}
        onClick={() => toggleSort(k)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            toggleSort(k);
          }
        }}
      >
        {label}
        {arrow(k)}
      </th>
    );
  }

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
        <strong>资金费明细</strong>
        <button type="button" onClick={exportCsv}>导出 CSV</button>
      </div>
      <div style={{ maxHeight: 360, overflowY: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {sortableTh("timestamp", "时间")}
              {sortableTh("symbol", "合约")}
              {sortableTh("amount_usdt", "金额（USDT）")}
              <th style={{ ...thStyle, cursor: "default" }}>交易 ID</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={`${r.tran_id}-${r.timestamp}`}>
                <td style={tdStyle}>{formatTimestamp(r.timestamp)}</td>
                <td style={tdStyle}>{r.symbol}</td>
                <td style={{ ...tdStyle, color: signColor(r.amount_usdt) }}>
                  {formatDecimalUsdt(r.amount_usdt)}
                </td>
                <td style={{ ...tdStyle, color: COLOR_MUTED, fontFamily: "monospace" }}>
                  {r.tran_id}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
