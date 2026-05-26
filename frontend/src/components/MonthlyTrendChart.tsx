import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { formatDecimalUsdt } from "../formatters";
import { COLOR_ACCENT, COLOR_BORDER, COLOR_OK } from "../themeColors";

interface Props {
  byMonth: Record<string, string>;
}

interface Row {
  month: string;
  amount: number;
  ema: number;
}

const EMA_WINDOW = 6;
const EMA_ALPHA = 2 / (EMA_WINDOW + 1);

const LEGEND: Record<string, string> = {
  amount: "月度金额",
  ema: "6月 EMA",
};

export function MonthlyTrendChart({ byMonth }: Props) {
  const data = useMemo<Row[]>(() => {
    const months = Object.keys(byMonth).sort();
    let ema = 0;
    return months.map((m, i) => {
      const amount = Number(byMonth[m] || 0);
      if (i === 0) ema = amount;
      else ema = EMA_ALPHA * amount + (1 - EMA_ALPHA) * ema;
      return { month: m, amount, ema };
    });
  }, [byMonth]);

  return (
    <div style={{ height: 280 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 16, right: 24, bottom: 8, left: 8 }}>
          <CartesianGrid stroke={COLOR_BORDER} strokeDasharray="3 3" />
          <XAxis dataKey="month" />
          <YAxis />
          <Tooltip
            formatter={(value, name) => {
              const key = String(name);
              const label = LEGEND[key] ?? key;
              const n = Number(value);
              if (!Number.isFinite(n)) return [String(value), label];
              return [formatDecimalUsdt(String(n)), label];
            }}
          />
          <Legend formatter={(v) => LEGEND[String(v)] ?? String(v)} />
          <Line
            type="monotone"
            dataKey="amount"
            stroke={COLOR_ACCENT}
            dot={false}
            name="amount"
          />
          <Line
            type="monotone"
            dataKey="ema"
            stroke={COLOR_OK}
            dot={false}
            strokeDasharray="4 2"
            name="ema"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
