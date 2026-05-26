import { useEffect, useRef, useState } from "react";
import { api } from "../api";

interface Props {
  value: string;
  onChange: (s: string) => void;
}

export function SymbolPicker({ value, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const [options, setOptions] = useState<string[]>([]);
  const blurTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reqIdRef = useRef(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    if (value.length < 2) {
      if (mountedRef.current) setOptions([]);
      return;
    }
    debounceTimer.current = setTimeout(async () => {
      const id = ++reqIdRef.current;
      const r = await api.get<{ symbols: string[] }>(
        `/symbols?q=${encodeURIComponent(value)}`,
      );
      if (!mountedRef.current) return;
      if (id !== reqIdRef.current) return;
      if (r.data) setOptions(r.data.symbols.slice(0, 10));
    }, 200);
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, [value]);

  useEffect(() => {
    return () => {
      if (blurTimer.current) clearTimeout(blurTimer.current);
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, []);

  function handleFocus() {
    if (blurTimer.current) {
      clearTimeout(blurTimer.current);
      blurTimer.current = null;
    }
    setOpen(true);
  }

  function handleBlur() {
    if (blurTimer.current) clearTimeout(blurTimer.current);
    blurTimer.current = setTimeout(() => setOpen(false), 150);
  }

  function select(o: string) {
    onChange(o);
    setOpen(false);
  }

  return (
    <div style={{ position: "relative" }}>
      <input
        data-testid="symbol-input"
        type="text"
        value={value}
        autoComplete="off"
        placeholder="如 BTCUSDT"
        onChange={(e) => onChange(e.target.value.toUpperCase())}
        onFocus={handleFocus}
        onBlur={handleBlur}
        style={{ width: "100%", boxSizing: "border-box" }}
      />
      {open && options.length > 0 && (
        <ul
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            margin: 0,
            padding: 0,
            listStyle: "none",
            background: "var(--color-bg, #fff)",
            border: "1px solid var(--color-border, #ccc)",
            maxHeight: 240,
            overflowY: "auto",
            zIndex: 10,
          }}
        >
          {options.map((o) => (
            <li
              key={o}
              onMouseDown={() => select(o)}
              style={{ padding: "6px 12px", cursor: "pointer" }}
            >
              {o}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
