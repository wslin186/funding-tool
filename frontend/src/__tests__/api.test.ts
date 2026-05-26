import { describe, it, expect, beforeEach, vi } from "vitest";
import { api } from "../api";
import { resetCsrf, csrfStore } from "../csrfStore";

describe("api", () => {
  beforeEach(() => {
    resetCsrf();
    vi.stubGlobal("fetch", vi.fn());
  });

  it("GET returns data wrapper on 2xx", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true, status: 200, json: async () => ({ status: "ok" }),
    });
    const r = await api.get("/health");
    expect(r).toEqual({ data: { status: "ok" } });
  });

  it("POST attaches X-Funding-Token from csrfStore", async () => {
    csrfStore._set("token-x");
    const f = vi.fn().mockResolvedValue({
      ok: true, status: 200, json: async () => ({}),
    });
    vi.stubGlobal("fetch", f);
    await api.post("/accounts", { name: "a" });
    const init = f.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)["X-Funding-Token"]).toBe("token-x");
    expect(init.method).toBe("POST");
    expect(init.credentials).toBe("same-origin");
  });

  it("non-2xx returns ApiError shape", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false, status: 400,
      json: async () => ({ error: { code: "validation_error", message: "bad", field: "symbol" } }),
    });
    const r = await api.get("/symbols");
    expect(r).toEqual({ error: { code: "validation_error", message: "bad", field: "symbol" } });
  });

  it("network failure returns network_error", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new TypeError("fail"));
    const r = await api.get("/health");
    expect(r.error?.code).toBe("network_error");
  });
});
