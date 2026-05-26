import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { HistoryPage } from "../components/HistoryPage";
import { csrfStore, resetCsrf } from "../csrfStore";
import type { AccountSummary, HistoryTaskStatus } from "../types";

const oneAccount: AccountSummary = {
  name: "main",
  label: "主账户",
  created_at: "2026-05-01T10:30:00Z",
  key_first6: "abc123",
  permissions: { read: true, trade: false, withdraw: false },
};

function jsonRes(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

async function flush() {
  // Drain microtask queue (fetch.then.then.then…).
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
}

describe("HistoryPage", () => {
  beforeEach(() => {
    resetCsrf();
    csrfStore._set("T");
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("loads accounts and renders the form with Chinese labels", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonRes({ accounts: [oneAccount] })),
    );

    render(<HistoryPage />);

    await waitFor(() => expect(screen.getByText("查询历史")).toBeTruthy());
    expect(screen.getByLabelText(/账户/)).toBeTruthy();
    expect(screen.getByLabelText(/开始/)).toBeTruthy();
    expect(screen.getByLabelText(/结束/)).toBeTruthy();
    expect(screen.getByLabelText(/合约/)).toBeTruthy();
  });

  it("submits POST /history with account_name and polls /history/result/{id} until done", async () => {
    const submit = { task_id: "abc", status: "pending" };
    const running: HistoryTaskStatus = {
      status: "running",
      progress: { processed: 2, total: 4 },
    };
    const finished: HistoryTaskStatus = {
      status: "done",
      result: {
        start: "2026-01-01T00:00:00Z",
        end: "2026-02-01T00:00:00Z",
        total: "123.45",
        by_symbol: { BTCUSDT: "100.0", ETHUSDT: "23.45" },
        by_month: { "2026-01": "123.45" },
        records: [
          {
            timestamp: "2026-01-15T08:00:00Z",
            symbol: "BTCUSDT",
            amount_usdt: "100.0",
            tran_id: "tx-1",
          },
        ],
      },
    };

    let resultCalls = 0;
    const fetchMock = vi.fn().mockImplementation((url: unknown, init?: RequestInit) => {
      const s = String(url);
      if (s.endsWith("/accounts")) return Promise.resolve(jsonRes({ accounts: [oneAccount] }));
      if (s.endsWith("/history") && (init?.method ?? "GET") === "POST") {
        return Promise.resolve(jsonRes(submit, 202));
      }
      if (s.includes("/history/result/")) {
        resultCalls += 1;
        return Promise.resolve(jsonRes(resultCalls >= 2 ? finished : running));
      }
      return Promise.resolve(jsonRes({}));
    });
    vi.stubGlobal("fetch", fetchMock);

    vi.useFakeTimers();

    render(<HistoryPage />);

    // accounts load — drain microtasks (mount → effect → fetch.then → setState)
    await act(async () => {
      await flush();
    });

    // account select should now contain the account
    const accSel = screen.getByLabelText(/账户/) as HTMLSelectElement;
    expect(accSel.value).toBe("main");

    // fill start/end
    fireEvent.change(screen.getByLabelText(/开始/), {
      target: { value: "2026-01-01T00:00" },
    });
    fireEvent.change(screen.getByLabelText(/结束/), {
      target: { value: "2026-02-01T00:00" },
    });

    fireEvent.click(screen.getByRole("button", { name: /查询/ }));

    // drain POST /history + first poll
    await act(async () => {
      await flush();
    });

    const postCall = fetchMock.mock.calls.find(
      (c) => (c[1] as RequestInit)?.method === "POST" && String(c[0]).endsWith("/history"),
    );
    expect(postCall).toBeTruthy();
    const body = JSON.parse((postCall![1] as RequestInit).body as string);
    expect(body.account_name).toBe("main");
    expect(typeof body.start).toBe("string");
    expect(typeof body.end).toBe("string");

    // advance timer to drive subsequent polls until done
    for (let i = 0; i < 5; i += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(2000);
      });
    }

    expect(screen.getByText(/123\.4500/)).toBeTruthy();
    expect(screen.getByText("月度趋势")).toBeTruthy();
    expect(screen.getByText(/按合约/)).toBeTruthy();
  });

  it("shows >90 days warning when the selected range is too wide", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonRes({ accounts: [oneAccount] })),
    );

    render(<HistoryPage />);
    await waitFor(() => expect(screen.getByLabelText(/账户/)).toBeTruthy());

    fireEvent.change(screen.getByLabelText(/开始/), {
      target: { value: "2026-01-01T00:00" },
    });
    fireEvent.change(screen.getByLabelText(/结束/), {
      target: { value: "2026-05-01T00:00" },
    });

    expect(screen.getByText(/查询时间较长/)).toBeTruthy();
  });

  it("shows a local validation error when account is missing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonRes({ accounts: [] })),
    );

    render(<HistoryPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /查询/ })).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: /查询/ }));

    await waitFor(() =>
      expect(screen.getByText(/请填写账户和起止时间|输入参数有问题/)).toBeTruthy(),
    );
  });
});
