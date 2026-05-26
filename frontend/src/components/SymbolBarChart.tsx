import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDecimalUsdt } from "../formatters";
import { COLOR_ACCENT, COLOR_BORDER } from "../themeColors";

interface Props {
  bySymbol: Record<string, string>;
}

interface Row {
  symbol: string;
  amount: number;
}

const TOP_N = 20;

export function SymbolBarChart({ bySymbol }: Props) {
  const data = useMemo<Row[]>(() => {
    return Object.entries(bySymbol)
      .map(([symbol, v]) => ({ symbol, amount: Number(v || 0) }))
      .filter((r) => Number.isFinite(r.amount))
      .sort((a, b) => Math.abs(b.amount) - Math.abs(a.amount))
      .slice(0, TOP_N);
  }, [bySymbol]);

  return (
    <div style={{ height: 320 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 16, right: 24, bottom: 8, left: 8 }}>
          <CartesianGrid stroke={COLOR_BORDER} strokeDasharray="3 3" />
          <XAxis
            type="number"
            tickFormatter={(v) => formatDecimalUsdt(String(v))}
            tick={{ fontSize: 11 }}
          />
          <YAxis type="category" dataKey="symbol" width={100} tick={{ fontSize: 11 }} />
          <Tooltip
            formatter={(value) => {
              const n = Number(value);
              if (!Number.isFinite(n)) return [String(value), "金额"];
              return [formatDecimalUsdt(String(n)), "金额"];
            }}
          />
          <Bar dataKey="amount" fill={COLOR_ACCENT} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
