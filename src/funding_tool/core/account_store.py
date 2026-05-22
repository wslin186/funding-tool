"""Multi-account credential store: YAML index + keyring-backed secrets.

YAML file layout (~/.config/funding-tool/accounts.yaml):

    default: my-main
    accounts:
      my-main:
        exchange: binance_usdm
        api_key_ref: keyring:funding-tool/my-main:key
        secret_ref: keyring:funding-tool/my-main:secret
        created_at: 2026-05-22T10:00:00Z
        permissions_verified_at: 2026-05-22T10:00:01Z

If a keyring backend is unavailable AND the caller passed allow_plaintext=True,
the YAML stores plaintext `api_key` / `api_secret` fields and adds
`_plaintext_warning: true`.
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, cast

import yaml

from funding_tool.core.errors import ConfigError, MissingCredentialsError
from funding_tool.core.models import ApiCredentials


class KeyringBackend(Protocol):
    def get_password(self, service: str, username: str) -> str | None: ...
    def set_password(self, service: str, username: str, value: str) -> None: ...
    def delete_password(self, service: str, username: str) -> None: ...


class PlaintextFallbackRequired(ConfigError):
    """Raised when no keyring backend is available and the caller has not opted into
    plaintext storage. Catch this in the CLI to prompt the user.

    Inherits from ConfigError (and therefore FundingToolError) so the top-level
    CLI handler catches it as a tool error rather than letting it bubble as an
    uncaught Exception.
    """


@dataclass(frozen=True)
class AccountRecord:
    name: str
    exchange: str
    created_at: datetime
    permissions_verified_at: datetime | None


_SERVICE_PREFIX = "funding-tool"


def _keyring_ref(name: str, kind: str) -> str:
    return f"keyring:{_SERVICE_PREFIX}/{name}:{kind}"


def _keyring_parse(ref: str) -> tuple[str, str]:
    # "keyring:funding-tool/my-main:key" → service "funding-tool/my-main", username "key"
    assert ref.startswith("keyring:")
    body = ref[len("keyring:") :]
    service, _, username = body.rpartition(":")
    return service, username


class AccountStore:
    def __init__(self, *, config_path: Path, keyring: KeyringBackend) -> None:
        self._path = config_path
        self._keyring = keyring
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"default": None, "accounts": {}}
        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"invalid YAML in {self._path}: {exc}") from exc
        data.setdefault("default", None)
        data.setdefault("accounts", {})
        return data

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Create tmp file with 0600 from the start so plaintext creds (fallback
        # mode) are never world-readable, even briefly. O_EXCL guards against a
        # stale tmp; this is a single-user CLI, so unlinking on collision is safe.
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            fd = os.open(tmp, flags, 0o600)
        except FileExistsError:
            tmp.unlink()
            fd = os.open(tmp, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(self._data, f, sort_keys=False)
        os.replace(tmp, self._path)

    def _keyring_available(self) -> bool:
        """Probe the keyring backend.

        Returns False only when no backend is installed at all. We deliberately
        keep a broad `except Exception` here rather than narrowing to specific
        keyring error classes: narrowing requires importing `keyring.errors`,
        which (a) couples this module to the real `keyring` package layout
        (the protocol allows any backend, including our test fake), and
        (b) the substring matching needed to distinguish "not installed" from
        "locked" via RuntimeError is fragile.
        Trade-off: a transient backend error (e.g. KeyringLocked) routes to the
        plaintext-fallback path. The CLI requires explicit `allow_plaintext=True`
        before writing plaintext, so this cannot silently downgrade security
        without user consent at the prompt layer.
        """
        try:
            self._keyring.get_password(_SERVICE_PREFIX, "__probe__")
        except Exception:
            return False
        return True

    def add(
        self,
        *,
        name: str,
        exchange: str,
        credentials: ApiCredentials,
        verified: bool = False,
        allow_plaintext: bool = False,
    ) -> None:
        accounts = self._data["accounts"]
        if name in accounts:
            raise ConfigError(f"account {name!r} already exists")

        entry: dict[str, Any] = {
            "exchange": exchange,
            "created_at": datetime.now(UTC).isoformat(),
            "permissions_verified_at": datetime.now(UTC).isoformat() if verified else None,
        }

        if self._keyring_available():
            self._keyring.set_password(
                f"{_SERVICE_PREFIX}/{name}", "key", credentials.api_key
            )
            self._keyring.set_password(
                f"{_SERVICE_PREFIX}/{name}", "secret", credentials.api_secret
            )
            entry["api_key_ref"] = _keyring_ref(name, "key")
            entry["secret_ref"] = _keyring_ref(name, "secret")
        else:
            if not allow_plaintext:
                raise PlaintextFallbackRequired(
                    "no keyring backend available; pass allow_plaintext=True to fall back"
                )
            entry["api_key"] = credentials.api_key
            entry["api_secret"] = credentials.api_secret
            entry["_plaintext_warning"] = True

        accounts[name] = entry
        if self._data["default"] is None:
            self._data["default"] = name
        self._save()

    def remove(self, name: str) -> None:
        accounts = self._data["accounts"]
        if name not in accounts:
            raise ConfigError(f"account {name!r} not found")
        entry = accounts.pop(name)

        # Clean up keyring entries if any (plaintext fallback has neither field):
        for ref_field in ("api_key_ref", "secret_ref"):
            ref = entry.get(ref_field)
            if not ref:
                continue
            service, username = _keyring_parse(ref)
            with contextlib.suppress(Exception):
                self._keyring.delete_password(service, username)

        if self._data["default"] == name:
            remaining = list(accounts.keys())
            self._data["default"] = remaining[0] if remaining else None
        self._save()

    def set_default(self, name: str) -> None:
        if name not in self._data["accounts"]:
            raise ConfigError(f"account {name!r} not found")
        self._data["default"] = name
        self._save()

    def get_default_name(self) -> str | None:
        return cast("str | None", self._data["default"])

    def list_accounts(self) -> list[AccountRecord]:
        out: list[AccountRecord] = []
        for name, entry in self._data["accounts"].items():
            created = datetime.fromisoformat(entry["created_at"])
            verified_raw = entry.get("permissions_verified_at")
            verified = datetime.fromisoformat(verified_raw) if verified_raw else None
            out.append(AccountRecord(
                name=name, exchange=entry["exchange"],
                created_at=created, permissions_verified_at=verified,
            ))
        return out

    def get_credentials(self, name: str) -> ApiCredentials:
        entry = self._data["accounts"].get(name)
        if entry is None:
            raise ConfigError(f"account {name!r} not found")

        if "api_key" in entry:  # plaintext fallback
            return ApiCredentials(
                api_key=entry["api_key"], api_secret=entry["api_secret"],
            )

        key_service, key_user = _keyring_parse(entry["api_key_ref"])
        sec_service, sec_user = _keyring_parse(entry["secret_ref"])
        api_key = self._keyring.get_password(key_service, key_user)
        api_secret = self._keyring.get_password(sec_service, sec_user)
        if not api_key or not api_secret:
            raise MissingCredentialsError(
                f"keyring entries for account {name!r} missing or empty"
            )
        return ApiCredentials(api_key=api_key, api_secret=api_secret)


def resolve_credentials(
    store: AccountStore,
    *,
    cli_api_key: str | None,
    cli_api_secret: str | None,
    env: dict[str, str],
    account_name: str | None,
) -> ApiCredentials:
    """Resolve credentials per the spec precedence: cli > env > named > default.

    Interactive prompting (priority 5) is handled in the CLI layer, not here.
    """
    # Both must be set together; reject XOR so a missing flag doesn't
    # silently fall through to a different credential source.
    if bool(cli_api_key) ^ bool(cli_api_secret):
        raise ConfigError("--api-key and --api-secret must be provided together")
    if cli_api_key and cli_api_secret:
        return ApiCredentials(api_key=cli_api_key, api_secret=cli_api_secret)

    env_key = env.get("BINANCE_API_KEY")
    env_secret = env.get("BINANCE_API_SECRET")
    if bool(env_key) ^ bool(env_secret):
        raise ConfigError(
            "BINANCE_API_KEY and BINANCE_API_SECRET must both be set"
        )
    if env_key and env_secret:
        return ApiCredentials(api_key=env_key, api_secret=env_secret)

    if account_name:
        return store.get_credentials(account_name)

    default = store.get_default_name()
    if default:
        return store.get_credentials(default)

    raise MissingCredentialsError(
        "no credentials found (no --api-key, no BINANCE_API_KEY env, no --account, no default)"
    )
