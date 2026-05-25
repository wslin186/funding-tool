"""Environment-driven settings. Loaded once at startup and frozen."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    public_origin: str
    auth_user: str
    auth_password_hash: bytes
    db_path: Path
    audit_log_path: Path
    tasks_dir: Path
    bind_host: str = "127.0.0.1"
    bind_port: int = 8001


def _required(name: str) -> str:
    v = os.environ.get(name)
    if v is None:
        raise KeyError(f"missing env var {name}")
    return v


def load_settings() -> Settings:
    public_origin = _required("FUNDING_PUBLIC_ORIGIN")
    if not public_origin.startswith("https://"):
        raise ValueError(f"FUNDING_PUBLIC_ORIGIN must be https://, got {public_origin!r}")
    return Settings(
        public_origin=public_origin.rstrip("/"),
        auth_user=_required("FUNDING_AUTH_USER"),
        auth_password_hash=_required("FUNDING_AUTH_PASSWORD_HASH").encode(),
        db_path=Path(_required("FUNDING_DB_PATH")),
        audit_log_path=Path(_required("FUNDING_AUDIT_LOG_PATH")),
        tasks_dir=Path(_required("FUNDING_TASKS_DIR")),
    )
