import { useEffect, useState } from "react";
import { api } from "../api";
import type { AccountSummary, ApiError } from "../types";
import { formatTimestamp } from "../formatters";
import { ErrorBanner } from "./ErrorBanner";
import { AccountForm } from "./AccountForm";

function permMark(v: boolean | null): string {
  if (v === null) return "?";
  return v ? "✓" : "×";
}

function permissionWarning(p: AccountSummary["permissions"]): string | null {
  const hasTrade = p.trade === true;
  const hasWithdraw = p.withdraw === true;
  if (!hasTrade && !hasWithdraw) return null;
  let which: string;
  if (hasTrade && hasWithdraw) which = "交易权限与提现权限";
  else if (hasTrade) which = "交易权限";
  else which = "提现权限";
  return `⚠ 该密钥拥有${which}，强烈建议改为只读。`;
}

export function AccountsPage() {
  const [accs, setAccs] = useState<AccountSummary[] | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [showForm, setShowForm] = useState(false);

  async function load() {
    const r = await api.get<{ accounts: AccountSummary[] }>("/accounts");
    if (r.error) {
      setError(r.error);
      return;
    }
    setAccs(r.data?.accounts ?? []);
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleDelete(name: string) {
    if (!window.confirm(`确定删除账户「${name}」？此操作不可撤销。`)) return;
    const r = await api.delete<void>(`/accounts/${encodeURIComponent(name)}`);
    if (r.error) {
      setError(r.error);
      return;
    }
    await load();
  }

  return (
    <div data-testid="page-accounts">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <h2 style={{ margin: 0 }}>账户</h2>
        {!showForm && (
          <button type="button" onClick={() => setShowForm(true)}>
            添加账户
          </button>
        )}
      </div>

      <ErrorBanner error={error} onDismiss={() => setError(null)} />

      {showForm && (
        <div style={{ marginBottom: 16 }}>
          <AccountForm
            onCancel={() => setShowForm(false)}
            onSuccess={() => {
              setShowForm(false);
              void load();
            }}
          />
        </div>
      )}

      {accs === null ? (
        <div className="card">加载中…</div>
      ) : accs.length === 0 ? (
        <div className="card">暂无账户，请添加。</div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: 16,
          }}
        >
          {accs.map((a) => {
            const warn = permissionWarning(a.permissions);
            return (
              <div key={a.name} className="card">
                <div style={{ fontWeight: 600, fontSize: 16 }}>
                  {a.label || a.name}
                </div>
                <div style={{ fontSize: 12, color: "var(--color-muted)" }}>
                  名称：{a.name}
                </div>
                <div style={{ fontFamily: "monospace", marginTop: 8 }}>
                  密钥：{a.key_first6}…
                </div>
                <div style={{ marginTop: 8 }}>
                  权限：只读{permMark(a.permissions.read)} · 交易
                  {permMark(a.permissions.trade)} · 提现
                  {permMark(a.permissions.withdraw)}
                </div>
                <div style={{ fontSize: 12, color: "var(--color-muted)", marginTop: 4 }}>
                  创建：{formatTimestamp(a.created_at)}
                </div>
                {warn && (
                  <div
                    role="alert"
                    style={{
                      marginTop: 12,
                      padding: "8px 12px",
                      background: "var(--color-err-bg)",
                      color: "var(--color-err)",
                      borderRadius: 4,
                      fontSize: 13,
                    }}
                  >
                    {warn}
                  </div>
                )}
                <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end" }}>
                  <button type="button" onClick={() => void handleDelete(a.name)}>
                    删除
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
