import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { AccountsPage } from "../components/AccountsPage";
import { csrfStore, resetCsrf } from "../csrfStore";
import type { AccountSummary } from "../types";

const oneAccount: AccountSummary = {
  name: "main",
  label: "主账户",
  created_at: "2026-05-01T10:30:00Z",
  key_first6: "abc123",
  permissions: { read: true, trade: false, withdraw: false },
};

function mockFetchOnceJson(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

describe("AccountsPage", () => {
  beforeEach(() => {
    resetCsrf();
    csrfStore._set("T");
  });

  it("loads and renders account cards with Chinese labels", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(mockFetchOnceJson({ accounts: [oneAccount] })),
    );

    render(<AccountsPage />);

    await waitFor(() => expect(screen.getByText("主账户")).toBeTruthy());
    expect(screen.getByText(/abc123/)).toBeTruthy();
    expect(screen.getByText(/只读/)).toBeTruthy();
  });

  it("shows red inline warning when trade or withdraw is true", async () => {
    const acc: AccountSummary = {
      ...oneAccount,
      permissions: { read: true, trade: true, withdraw: false },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(mockFetchOnceJson({ accounts: [acc] })),
    );

    render(<AccountsPage />);

    await waitFor(() => expect(screen.getByText(/交易权限/)).toBeTruthy());
  });

  it("delete requires confirm() and POSTs DELETE", async () => {
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mockFetchOnceJson({ accounts: [oneAccount] }))
      .mockResolvedValueOnce({ ok: true, status: 204, json: async () => ({}) })
      .mockResolvedValueOnce(mockFetchOnceJson({ accounts: [] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<AccountsPage />);

    await waitFor(() => expect(screen.getByText("主账户")).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "删除" }));

    await waitFor(() => {
      const calledDelete = fetchMock.mock.calls.some(
        (c) => (c[1] as RequestInit)?.method === "DELETE",
      );
      expect(calledDelete).toBe(true);
    });
  });
});
