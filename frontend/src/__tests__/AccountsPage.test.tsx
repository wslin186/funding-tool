import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
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

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
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

  it("composes warning for BOTH trade and withdraw permissions", async () => {
    const acc: AccountSummary = {
      ...oneAccount,
      permissions: { read: true, trade: true, withdraw: true },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(mockFetchOnceJson({ accounts: [acc] })),
    );

    render(<AccountsPage />);

    await waitFor(() => {
      const warn = screen.getByRole("alert");
      expect(warn.textContent).toMatch(/交易权限/);
      expect(warn.textContent).toMatch(/提现权限/);
    });
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

    fireEvent.click(screen.getByRole("button", { name: /删除账户 main/ }));

    await waitFor(() => {
      const calledDelete = fetchMock.mock.calls.some(
        (c) => (c[1] as RequestInit)?.method === "DELETE",
      );
      expect(calledDelete).toBe(true);
    });
  });

  it("submits POST /accounts with name/label/api_key/api_secret and reloads", async () => {
    const fetchMock = vi
      .fn()
      // initial GET — empty list, so 添加账户 button shows
      .mockResolvedValueOnce(mockFetchOnceJson({ accounts: [] }))
      // POST — returns 201 with the created account
      .mockResolvedValueOnce(mockFetchOnceJson({ account: oneAccount }, 201))
      // reload GET — returns the new account
      .mockResolvedValueOnce(mockFetchOnceJson({ accounts: [oneAccount] }));
    vi.stubGlobal("fetch", fetchMock);

    render(<AccountsPage />);

    // wait for initial load (empty state)
    await waitFor(() => expect(screen.getByText(/暂无账户/)).toBeTruthy());

    // open the form
    fireEvent.click(screen.getByRole("button", { name: "添加账户" }));

    // fill in all 4 fields
    fireEvent.change(screen.getByLabelText(/名称（唯一）/), {
      target: { value: "main" },
    });
    fireEvent.change(screen.getByLabelText(/备注/), {
      target: { value: "主账户" },
    });
    fireEvent.change(screen.getByLabelText(/API Key/), {
      target: { value: "key-xyz-1234567890" },
    });
    fireEvent.change(screen.getByLabelText(/API Secret/), {
      target: { value: "secret-xyz-1234567890" },
    });

    // submit
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    // wait for POST call and re-render
    await waitFor(() => expect(screen.getByText("主账户")).toBeTruthy());

    // find the POST call and assert its shape
    const postCall = fetchMock.mock.calls.find(
      (c) => (c[1] as RequestInit)?.method === "POST",
    );
    expect(postCall).toBeTruthy();
    const init = postCall![1] as RequestInit;
    expect(init.method).toBe("POST");
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({
      name: "main",
      label: "主账户",
      api_key: "key-xyz-1234567890",
      api_secret: "secret-xyz-1234567890",
    });
  });
});
