export type Side = "LONG" | "SHORT";
export type SizeMode = "BASE" | "QUOTE" | "RATE_ONLY";

export interface BacktestRequest {
  symbol: string;
  side: Side;
  start: string;
  end: string;
  size_mode: SizeMode;
  size?: string;
}

export interface FundingPayment {
  timestamp: string;
  rate: string;
  mark_price: string;
  quantity_base: string | null;
  notional_quote: string | null;
  payment_quote: string | null;
}

export interface BacktestResponse {
  input: BacktestRequest;
  event_count: number;
  total_quote: string | null;
  total_base: string | null;
  cumulative_rate_pct: string;
  avg_rate_pct: string;
  annualized_pct: string;
  payments: FundingPayment[];
}

export interface HistoryRequest {
  account: string;
  start: string;
  end: string;
  symbol?: string;
}

export interface IncomeRecord {
  timestamp: string;
  symbol: string;
  amount_usdt: string;
  tran_id: string;
}

export interface HistoryPayload {
  start: string;
  end: string;
  total_usdt: string;
  by_symbol: Record<string, string>;
  by_month: Record<string, string>;
  records: IncomeRecord[];
}

export type TaskStatus = "pending" | "running" | "done" | "error";

export interface HistoryTaskStatus {
  status: TaskStatus;
  progress?: { processed: number; total: number };
  result?: HistoryPayload;
  error?: { code: string; message: string };
}

export interface AccountSummary {
  name: string;
  label: string;
  created_at: string;
  key_first6: string;
  permissions: { read: boolean | null; trade: boolean | null; withdraw: boolean | null };
}

export interface ApiError {
  code: string;
  message: string;
  field?: string;
  error_id?: string;
}
