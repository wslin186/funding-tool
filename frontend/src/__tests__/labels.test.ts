import { describe, it, expect } from "vitest";
import { fieldLabel, errorMessage, sideLabel, sizeModeLabel, taskStatusLabel } from "../labels";

describe("labels", () => {
  it("translates every BacktestResponse field", () => {
    const fields = [
      "event_count", "cumulative_rate_pct", "avg_rate_pct",
      "annualized_pct", "total_quote", "total_base",
    ];
    for (const f of fields) {
      expect(fieldLabel(f)).not.toBe(f);
      expect(fieldLabel(f)).toMatch(/[一-龥]/);
    }
  });

  it("translates every error code to Chinese", () => {
    const codes = [
      "web_auth_required", "web_auth_locked", "csrf_mismatch",
      "validation_error", "range_too_large", "unknown_symbol",
      "exchange_auth_error", "exchange_rate_limit",
      "network_error", "exchange_error", "server_error",
    ];
    for (const c of codes) {
      expect(errorMessage(c)).toMatch(/[一-龥]/);
    }
  });

  it("unknown code falls back to generic Chinese message", () => {
    expect(errorMessage("totally_unknown")).toMatch(/未知错误/);
  });

  it("side LONG/SHORT and size_mode BASE/QUOTE/RATE_ONLY translated", () => {
    expect(sideLabel("LONG")).toBe("多头");
    expect(sideLabel("SHORT")).toBe("空头");
    expect(sizeModeLabel("BASE")).toBe("基础币数量");
    expect(sizeModeLabel("QUOTE")).toBe("USDT 名义");
    expect(sizeModeLabel("RATE_ONLY")).toBe("仅看费率");
  });

  it("translates renamed total field and taskStatus failed", () => {
    expect(fieldLabel("total")).toMatch(/[一-龥]/);
  });

  it("errorMessage uses explicit fallback before generic", () => {
    expect(errorMessage("totally_unknown", "自定义提示")).toBe("自定义提示");
  });

  it("translates task status including failed", () => {
    expect(taskStatusLabel("pending")).toBe("排队中");
    expect(taskStatusLabel("running")).toBe("查询中");
    expect(taskStatusLabel("done")).toBe("已完成");
    expect(taskStatusLabel("failed")).toBe("失败");
  });
});
