import { describe, it, expect, beforeEach, vi } from "vitest";
import { csrfStore, resetCsrf } from "../csrfStore";

describe("csrfStore", () => {
  beforeEach(() => { resetCsrf(); });

  it("fetches token from /api/csrf and caches it", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ token: "abc123" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const t1 = await csrfStore.getToken();
    const t2 = await csrfStore.getToken();
    expect(t1).toBe("abc123");
    expect(t2).toBe("abc123");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("refresh forces a new GET", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ token: "old" }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ token: "new" }) });
    vi.stubGlobal("fetch", fetchMock);

    expect(await csrfStore.getToken()).toBe("old");
    await csrfStore.refresh();
    expect(await csrfStore.getToken()).toBe("new");
  });
});
