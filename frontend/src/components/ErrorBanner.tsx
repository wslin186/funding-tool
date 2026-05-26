import type { ApiError } from "../types";
import { errorMessage } from "../labels";

interface Props {
  error: ApiError | null;
  onDismiss?: () => void;
}

export function ErrorBanner({ error, onDismiss }: Props) {
  if (!error) return null;
  const msg = errorMessage(error.code, error.message);
  const fieldSuffix = error.field ? `（字段：${error.field}）` : "";
  const idSuffix = error.error_id ? `[ID: ${error.error_id}]` : "";
  return (
    <div className="error-banner" role="alert">
      <span>{msg}{fieldSuffix} {idSuffix}</span>
      {onDismiss && <button onClick={onDismiss} style={{ float: "right", background: "none", border: 0, cursor: "pointer", color: "inherit" }}>×</button>}
    </div>
  );
}
