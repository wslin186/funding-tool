import { describe, it, expect, beforeAll } from "vitest";

declare const require: (id: string) => unknown;
const { readFileSync } = require("node:fs") as { readFileSync: (p: string, enc: string) => string };
const { resolve } = require("node:path") as { resolve: (...p: string[]) => string };
declare const process: { cwd(): string };

const css = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8");

describe("design tokens", () => {
  beforeAll(() => {
    const style = document.createElement("style");
    style.textContent = css;
    document.head.appendChild(style);
  });

  it("exposes color tokens via :root", () => {
    const root = getComputedStyle(document.documentElement);
    for (const t of [
      "--color-bg", "--color-surface", "--color-text",
      "--color-ok", "--color-err", "--color-warn", "--color-accent",
      "--space-1", "--space-2", "--space-3", "--radius-1",
    ]) {
      expect(root.getPropertyValue(t).trim()).not.toBe("");
    }
  });
});
