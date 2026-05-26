const FIELD: Record<string, string> = {
  event_count: "期数",
  total_quote: "合计（USDT）",
  total_base: "合计（基础币）",
  cumulative_rate_pct: "累计费率",
  avg_rate_pct: "平均费率",
  annualized_pct: "年化",
  timestamp: "时间",
  rate: "费率",
  mark_price: "标记价",
  quantity_base: "持仓（基础币）",
  notional_quote: "名义（USDT）",
  payment_quote: "本期收益（USDT）",
  symbol: "合约",
  amount_usdt: "金额（USDT）",
  tran_id: "交易 ID",
  by_symbol: "按合约",
  by_month: "按月",
};

const ERROR: Record<string, string> = {
  web_auth_required: "请先登录",
  web_auth_locked: "登录次数过多，请 5 分钟后重试",
  csrf_mismatch: "安全令牌失效，请刷新页面",
  validation_error: "输入参数有问题",
  range_too_large: "查询时间范围超过上限",
  unknown_symbol: "币安没有这个合约，请检查拼写",
  exchange_auth_error: "Binance 密钥无效或权限不足",
  exchange_rate_limit: "币安限流，请稍后重试",
  network_error: "网络异常，请稍后重试",
  exchange_error: "币安接口异常",
  server_error: "服务器内部错误（已记录）",
};

export function fieldLabel(field: string): string {
  return FIELD[field] ?? field;
}

export function errorMessage(code: string, fallback?: string): string {
  return ERROR[code] ?? fallback ?? "未知错误，请稍后重试";
}

export function sideLabel(s: "LONG" | "SHORT"): string {
  return s === "LONG" ? "多头" : "空头";
}

export function sizeModeLabel(m: "BASE" | "QUOTE" | "RATE_ONLY"): string {
  if (m === "BASE") return "基础币数量";
  if (m === "QUOTE") return "USDT 名义";
  return "仅看费率";
}

export function taskStatusLabel(s: string): string {
  return ({ pending: "排队中", running: "查询中", done: "已完成", error: "失败" } as Record<string, string>)[s] ?? s;
}
