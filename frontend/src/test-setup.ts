import "@testing-library/jest-dom/vitest";

// jsdom polyfill: Recharts' ResponsiveContainer requires ResizeObserver.
const g = globalThis as unknown as {
  ResizeObserver?: unknown;
};
if (typeof g.ResizeObserver === "undefined") {
  class ResizeObserverMock {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  g.ResizeObserver = ResizeObserverMock;
}

// jsdom polyfill: URL.createObjectURL / revokeObjectURL for CSV export.
const urlAny = URL as unknown as {
  createObjectURL?: (b: Blob) => string;
  revokeObjectURL?: (s: string) => void;
};
if (typeof urlAny.createObjectURL !== "function") {
  urlAny.createObjectURL = () => "blob:test";
}
if (typeof urlAny.revokeObjectURL !== "function") {
  urlAny.revokeObjectURL = () => {};
}
