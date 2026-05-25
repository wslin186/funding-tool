"""JSON-lines audit log writer. Never logs api_key / api_secret / master_fingerprint."""
from __future__ import annotations

import json
import logging
import logging.handlers
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

_FORBIDDEN_KEYS = {"api_key", "api_secret", "master_key", "master_fingerprint", "password"}


class AuditLogger:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Logger name keyed on path.name; assumes one global AuditLogger per filename.
        self._logger = logging.getLogger(f"funding_tool.audit.{path.name}")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        for h in list(self._logger.handlers):
            self._logger.removeHandler(h)
        handler = logging.handlers.WatchedFileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(handler)

    def log(
        self,
        *,
        action: str,
        ip: str,
        user: str | None,
        result: Literal["ok", "fail"],
        target: str | None = None,
        error_code: str | None = None,
        error_id: str | None = None,
        extras: dict[str, Any] | None = None,
    ) -> None:
        if extras:
            bad = _FORBIDDEN_KEYS.intersection(extras)
            if bad:
                raise ValueError(f"forbidden audit keys: {bad}")
            for k, v in extras.items():
                if v is not None and not isinstance(v, (str, int, bool)):
                    raise ValueError(
                        f"audit extras value for {k!r} must be scalar (str/int/bool/None), got {type(v).__name__}"
                    )
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "ip": ip,
            "user": user,
            "action": action,
            "target": target,
            "result": result,
            "error_code": error_code,
            "error_id": error_id,
        }
        if extras:
            record.update(extras)
        self._logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":")))

    def close(self) -> None:
        for h in list(self._logger.handlers):
            h.close()
            self._logger.removeHandler(h)
