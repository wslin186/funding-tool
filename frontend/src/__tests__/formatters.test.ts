import { describe, it, expect } from "vitest";
import {
  formatDecimalUsdt, formatPercent, formatTimestamp,
  csvEscape,
} from "../formatters";

describe("formatters", () => {
  it("formats Decimal string to 4dp + 千分位", () => {
    expect(formatDecimalUsdt("12345.6789012")).toBe("12,345.6789");
    expect(formatDecimalUsdt("-0.5")).toBe("-0.5000");
  });

  it("formats percent with sign and 4dp", () => {
    expect(formatPercent("0.0123")).toBe("+0.0123%");
    expect(formatPercent("-0.0001")).toBe("-0.0001%");
    expect(formatPercent("0")).toBe("0.0000%");
  });

  it("formats ISO timestamp to local YYYY-MM-DD HH:mm", () => {
    expect(formatTimestamp("2026-05-25T08:00:00Z")).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/);
  });

  it("csvEscape wraps commas/quotes/newlines and doubles internal quotes", () => {
    expect(csvEscape("a,b")).toBe("\"a,b\"");
    expect(csvEscape("he said \"hi\"")).toBe("\"he said \"\"hi\"\"\"");
    expect(csvEscape("plain")).toBe("plain");
  });
});
