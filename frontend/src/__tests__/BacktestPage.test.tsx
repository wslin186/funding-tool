import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { BacktestPage } from "../components/BacktestPage";
import { csrfStore, resetCsrf } from "../csrfStore";

const mockResp = {
  event_count: 3,
  total_quote: "12.3456",
  total_base: null,
  cumulative_rate_pct: "0.0123",
  avg_rate_pct: "0.0041",
  annualized_pct: "1.5",
  payments: [
    {
      timestamp: "2026-04-25T08:00:00Z",
      rate: "0.0001",
      mark_price: "70000",
      quantity_base: "0.14",
      notional_quote: "9800",
      payment_quote: "0.98",
    },
    {
      timestamp: "2026-04-25T16:00:00Z",
      rate: "-0.00005",
      mark_price: "70100",
      quantity_base: "0.14",
      notional_quote: "9814",
      payment_quote: "-0.49",
    },
    {
      timestamp: "2026-04-26T00:00:00Z",
      rate: "0.0002",
      mark_price: "70200",
      quantity_base: "0.14",
      notional_quote: "9828",
      payment_quote: "1.96",
    },
  ],
};

function jsonRes(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

function makeFetchMock(backtestBody: unknown) {
  return vi.fn().mockImplementation((url: unknown) => {
    const s = String(url);
    if (s.includes("/symbols")) return Promise.resolve(jsonRes({ symbols: ["BTCUSDT"] }));
    if (s.includes("/backtest")) return Promise.resolve(jsonRes(backtestBody));
    if (s.includes("/csrf")) return Promise.resolve(jsonRes({ token: "T" }));
    return Promise.resolve(jsonRes({}));
  });
}

describe("BacktestPage", () => {
  beforeEach(() => {
    resetCsrf();
    csrfStore._set("T");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("renders form with Chinese labels and submits to /backtest", async () => {
    vi.stubGlobal("fetch", makeFetchMock(mockResp));

    render(<BacktestPage />);

    expect(screen.getByText(/合约/)).toBeTruthy();
    const runBtn = screen.getByRole("button", { name: "跑回测" });
    expect(runBtn).toBeTruthy();

    fireEvent.change(screen.getByTestId("symbol-input"), {
      target: { value: "BTCUSDT" },
    });

    fireEvent.click(screen.getByRole("button", { name: "跑回测" }));

    await waitFor(() => expect(screen.getByText(/期数/)).toBeTruthy());
    expect(screen.getByText(/12\.3456/)).toBeTruthy();
  });

  it("RATE_ONLY mode shows 合计 as —", async () => {
    vi.stubGlobal(
      "fetch",
      makeFetchMock({ ...mockResp, total_quote: null, total_base: null }),
    );

    render(<BacktestPage />);

    fireEvent.change(screen.getByTestId("symbol-input"), {
      target: { value: "BTCUSDT" },
    });
    fireEvent.change(screen.getByTestId("size-mode"), {
      target: { value: "RATE_ONLY" },
    });

    fireEvent.click(screen.getByRole("button", { name: "跑回测" }));

    await waitFor(() => expect(screen.getByText(/期数/)).toBeTruthy());
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});
