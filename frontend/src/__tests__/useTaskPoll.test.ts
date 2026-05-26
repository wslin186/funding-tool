import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTaskPoll } from "../useTaskPoll";
import { csrfStore, resetCsrf } from "../csrfStore";
import type { HistoryTaskStatus } from "../types";

function jsonRes(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

// Flush all microtasks plus N timer ticks. Used to let polling chain run.
async function flush() {
  // jest/vitest microtask drain
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
}

describe("useTaskPoll", () => {
  beforeEach(() => {
    resetCsrf();
    csrfStore._set("T");
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("returns null status when task_id is null", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const { result } = renderHook(() => useTaskPoll(null));
    expect(result.current.status).toBeNull();
    expect(result.current.error).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("polls every 2 seconds and stops on done", async () => {
    vi.useFakeTimers();
    const pending: HistoryTaskStatus = {
      status: "running",
      progress: { processed: 5, total: 10 },
    };
    const finished: HistoryTaskStatus = {
      status: "done",
      result: {
        start: "2026-01-01T00:00:00Z",
        end: "2026-02-01T00:00:00Z",
        total: "100.0",
        by_symbol: { BTCUSDT: "100.0" },
        by_month: { "2026-01": "100.0" },
        records: [],
      },
    };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonRes(pending))
      .mockResolvedValueOnce(jsonRes(pending))
      .mockResolvedValueOnce(jsonRes(finished));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTaskPoll("task-123"));

    // first fetch happens immediately — let microtasks settle
    await act(async () => {
      await flush();
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(result.current.status?.status).toBe("running");

    // advance 2s → second poll fires and resolves
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // advance another 2s → third poll resolves done, polling stops
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(result.current.status?.status).toBe("done");

    // advance more — no further polls
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("honors a custom intervalMs override", async () => {
    vi.useFakeTimers();
    const pending: HistoryTaskStatus = {
      status: "running",
      progress: { processed: 1, total: 10 },
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonRes(pending));
    vi.stubGlobal("fetch", fetchMock);

    renderHook(() => useTaskPoll("tid", 100));

    // first fetch happens immediately
    await act(async () => {
      await flush();
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    // advance just past 100ms → second poll fires (would not at 2000ms default)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120);
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);

    // and again
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120);
    });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("stops polling on failed terminal status", async () => {
    vi.useFakeTimers();
    const failed: HistoryTaskStatus = {
      status: "failed",
      error: { code: "exchange_error", message: "boom" },
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonRes(failed));
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTaskPoll("task-x"));

    await act(async () => {
      await flush();
    });
    expect(result.current.status?.status).toBe("failed");
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sets error and stops polling when api returns error", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        jsonRes({ error: { code: "server_error", message: "oops" } }, 500),
      );
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useTaskPoll("task-err"));

    await act(async () => {
      await flush();
    });
    expect(result.current.error?.code).toBe("server_error");

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("cleans up on unmount and stops polling", async () => {
    vi.useFakeTimers();
    const pending: HistoryTaskStatus = {
      status: "running",
      progress: { processed: 1, total: 10 },
    };
    const fetchMock = vi.fn().mockResolvedValue(jsonRes(pending));
    vi.stubGlobal("fetch", fetchMock);

    const { unmount } = renderHook(() => useTaskPoll("task-u"));

    await act(async () => {
      await flush();
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);

    unmount();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
