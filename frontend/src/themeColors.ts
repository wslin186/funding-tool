// Resolved CSS-variable color tokens for libraries (e.g. Recharts) that write
// values directly into SVG attributes, which the browser does NOT resolve via
// CSS custom properties. Read the values once from :root and fall back to the
// literal hex values defined in src/index.css.
//
// Fallback hex values mirror the tokens in src/index.css so callers always get
// a non-empty string even when window/document is not available (SSR, tests).

function cssVar(name: string, fallback: string): string {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return fallback;
  }
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

export const COLOR_ACCENT = cssVar("--color-accent", "#1f6c9f");
export const COLOR_OK = cssVar("--color-ok", "#2f6b3a");
export const COLOR_ERR = cssVar("--color-err", "#9f2f2d");
export const COLOR_BORDER = cssVar("--color-border", "#d8d6cf");
export const COLOR_MUTED = cssVar("--color-muted", "#6b6b6b");

export { cssVar };
