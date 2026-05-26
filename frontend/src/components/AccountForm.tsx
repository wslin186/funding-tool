import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { AccountSummary, ApiError } from "../types";
import { ErrorBanner } from "./ErrorBanner";

interface Props {
  onSuccess: (acc: AccountSummary) => void;
  onCancel: () => void;
}

export function AccountForm({ onSuccess, onCancel }: Props) {
  const [name, setName] = useState("");
  const [label, setLabel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const mounted = useRef(true);

  useEffect(
    () => () => {
      mounted.current = false;
    },
    [],
  );

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    const r = await api.post<{ account: AccountSummary }>("/accounts", {
      name,
      label,
      api_key: apiKey,
      api_secret: apiSecret,
    });
    if (!mounted.current) return;
    setBusy(false);
    if (r.error) {
      if (mounted.current) setError(r.error);
      return;
    }
    if (r.data && mounted.current) onSuccess(r.data.account);
  }

  return (
    <form onSubmit={handleSubmit} className="card" style={{ maxWidth: 480 }}>
      <ErrorBanner error={error} onDismiss={() => setError(null)} />
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span>名称（唯一）</span>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            autoComplete="off"
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span>备注</span>
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            autoComplete="off"
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span>API Key</span>
          <input
            type="text"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            required
            autoComplete="off"
          />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span>API Secret</span>
          <input
            type="password"
            value={apiSecret}
            onChange={(e) => setApiSecret(e.target.value)}
            required
            autoComplete="off"
          />
        </label>
        <p style={{ fontSize: 12, color: "var(--color-muted)", margin: 0 }}>
          密钥在服务端以 AES-GCM 加密存储；强烈建议在币安创建只读权限的密钥。
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="submit" disabled={busy}>
            {busy ? "验证中…" : "保存"}
          </button>
          <button type="button" onClick={onCancel} disabled={busy}>
            取消
          </button>
        </div>
      </div>
    </form>
  );
}
