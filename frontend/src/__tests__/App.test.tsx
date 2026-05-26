import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import App from "../App";
import { resetCsrf } from "../csrfStore";

describe("App", () => {
  beforeEach(() => {
    resetCsrf();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true, status: 200, json: async () => ({ token: "T" }),
    }));
  });

  it("renders three Chinese tabs and defaults to 回测", async () => {
    render(<App />);
    expect(screen.getByRole("tab", { name: "回测" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "历史" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "账户" })).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("page-backtest")).toBeTruthy());
  });

  it("switches between tabs on click", async () => {
    render(<App />);
    fireEvent.click(screen.getByRole("tab", { name: "账户" }));
    expect(screen.getByTestId("page-accounts")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "历史" }));
    expect(screen.getByTestId("page-history")).toBeTruthy();
  });
});
