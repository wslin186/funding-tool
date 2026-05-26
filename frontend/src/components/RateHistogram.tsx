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
import type { FundingPayment } from "../types";
import { COLOR_ACCENT, COLOR_BORDER } from "../themeColors";

interface Props {
  payments: FundingPayment[];
}

interface Bin {
  bin: string;
  count: number;
  k: number;
}

const STEP = 0.00005;

export function RateHistogram({ payments }: Props) {
  const data = useMemo<Bin[]>(() => {
    const counts = new Map<number, number>();
    for (const p of payments) {
      const r = Number(p.rate || 0);
      if (!Number.isFinite(r)) continue;
      const k = Math.floor(r / STEP);
      counts.set(k, (counts.get(k) ?? 0) + 1);
    }
    const keys = Array.from(counts.keys()).sort((a, b) => a - b);
    return keys.map((k) => ({
      k,
      bin: `${(k * STEP * 100).toFixed(4)}%`,
      count: counts.get(k) ?? 0,
    }));
  }, [payments]);

  return (
    <div style={{ height: 240 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 16, right: 24, bottom: 8, left: 8 }}>
          <CartesianGrid stroke={COLOR_BORDER} strokeDasharray="3 3" />
          <XAxis dataKey="bin" />
          <YAxis allowDecimals={false} />
          <Tooltip />
          <Bar dataKey="count" fill={COLOR_ACCENT} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
