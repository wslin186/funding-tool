import { useMemo } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FundingPayment } from "../types";
import { formatDecimalUsdt, formatTimestamp } from "../formatters";
import { COLOR_ACCENT, COLOR_BORDER, COLOR_OK } from "../themeColors";

interface Props {
  payments: FundingPayment[];
}

interface Row {
  t: string;
  rate_pct: number;
  payment: number;
  cum: number;
}

const LEGEND: Record<string, string> = {
  rate_pct: "费率",
  payment: "本期收益",
  cum: "累计 P&L",
};

export function PayoutTimelineChart({ payments }: Props) {
  const data = useMemo<Row[]>(() => {
    let cum = 0;
    return payments.map((p) => {
      cum += Number(p.payment_quote || 0);
      return {
        t: formatTimestamp(p.timestamp),
        rate_pct: Number(p.rate || 0) * 100,
        payment: Number(p.payment_quote || 0),
        cum,
      };
    });
  }, [payments]);

  return (
    <div style={{ height: 320 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={data} margin={{ top: 16, right: 24, bottom: 8, left: 8 }}>
          <CartesianGrid stroke={COLOR_BORDER} strokeDasharray="3 3" />
          <XAxis dataKey="t" />
          <YAxis yAxisId="left" />
          <YAxis yAxisId="right" orientation="right" />
          <Tooltip
            formatter={(value, name) => {
              const key = String(name);
              const label = LEGEND[key] ?? key;
              const n = Number(value);
              if (!Number.isFinite(n)) return [String(value), label];
              if (key === "rate_pct") return [`${n.toFixed(4)}%`, label];
              if (key === "payment" || key === "cum") {
                return [formatDecimalUsdt(String(n)), label];
              }
              return [String(value), label];
            }}
          />
          <Legend formatter={(v) => LEGEND[String(v)] ?? String(v)} />
          <Bar
            yAxisId="right"
            dataKey="rate_pct"
            fill={COLOR_ACCENT}
            name="rate_pct"
          />
          <Line
            yAxisId="left"
            type="monotone"
            dataKey="cum"
            stroke={COLOR_OK}
            dot={false}
            name="cum"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
