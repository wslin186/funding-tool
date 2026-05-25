"""AES-GCM encrypted SQLite store for Binance API credentials.

Independent from CLI keyring. Master key supplied at construction time.
Each row stores: key_version || nonce(12) || ciphertext || tag(16).
"""
from __future__ import annotations

import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from funding_tool.core.models import ApiCredentials

_CANARY_PLAINTEXT = b"funding-tool-canary-v1"


@dataclass(frozen=True)
class AccountRecord:
    name: str
    label: str
    created_at: datetime
    key_first6: str
    perm_read: bool | None = None
    perm_trade: bool | None = None
    perm_withdraw: bool | None = None


class SecretStore:
    def __init__(
        self,
        db_path: Path,
        *,
        master_key: bytes,
        prev_key: bytes | None = None,
        active_version: int = 1,
    ) -> None:
        if len(master_key) != 32:
            raise ValueError("master_key must be 32 bytes")
        self._db_path = db_path
        self._keys: dict[int, AESGCM] = {active_version: AESGCM(master_key)}
        if prev_key is not None:
            if len(prev_key) != 32:
                raise ValueError("prev_key must be 32 bytes")
            self._keys[active_version - 1] = AESGCM(prev_key)
        self._active_version = active_version

    @asynccontextmanager
    async def _connect(self) -> AsyncIterator[aiosqlite.Connection]:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("PRAGMA busy_timeout=5000")
            await db.execute("PRAGMA synchronous=NORMAL")
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    async def init_schema(self) -> None:
        async with self._connect() as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    name TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    key_first6 TEXT NOT NULL,
                    key_version INTEGER NOT NULL,
                    nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL,
                    rotation_state TEXT,
                    perm_read INTEGER,
                    perm_trade INTEGER,
                    perm_withdraw INTEGER,
                    perm_checked_at TEXT
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS canary (
                    id INTEGER PRIMARY KEY CHECK (id=1),
                    key_version INTEGER NOT NULL,
                    nonce BLOB NOT NULL,
                    ciphertext BLOB NOT NULL
                )
            """)
            cur = await db.execute("SELECT 1 FROM canary WHERE id=1")
            if not await cur.fetchone():
                nonce, ct = self._encrypt(_CANARY_PLAINTEXT)
                await db.execute(
                    "INSERT INTO canary(id, key_version, nonce, ciphertext) VALUES (1, ?, ?, ?)",
                    (self._active_version, nonce, ct),
                )
            await db.commit()

    async def verify_canary(self) -> None:
        async with self._connect() as db:
            cur = await db.execute("SELECT key_version, nonce, ciphertext FROM canary WHERE id=1")
            row = await cur.fetchone()
            if row is None:
                raise RuntimeError("canary row missing")
            kv, nonce, ct = row
            pt = self._decrypt(int(kv), nonce, ct)
            if pt != _CANARY_PLAINTEXT:
                raise RuntimeError("canary plaintext mismatch")

    async def add_account(
        self, name: str, label: str, creds: ApiCredentials
    ) -> None:
        if not name.strip():
            raise ValueError("name required")
        payload = json.dumps({
            "api_key": creds.api_key,
            "api_secret": creds.api_secret,
            "passphrase": creds.passphrase,
        }).encode()
        nonce, ct = self._encrypt(payload)
        now = datetime.now(timezone.utc).isoformat()
        async with self._connect() as db:
            try:
                await db.execute(
                    """INSERT INTO accounts
                       (name, label, created_at, key_first6, key_version, nonce, ciphertext)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (name, label, now, creds.api_key[:6], self._active_version, nonce, ct),
                )
                await db.commit()
            except aiosqlite.IntegrityError as e:
                raise ValueError(f"account {name!r} already exists") from e

    async def list_accounts(self) -> list[AccountRecord]:
        async with self._connect() as db:
            cur = await db.execute(
                "SELECT name, label, created_at, key_first6, "
                "       perm_read, perm_trade, perm_withdraw "
                "FROM accounts ORDER BY created_at"
            )
            return [
                AccountRecord(
                    name=r[0], label=r[1],
                    created_at=datetime.fromisoformat(r[2]),
                    key_first6=r[3],
                    perm_read=None if r[4] is None else bool(r[4]),
                    perm_trade=None if r[5] is None else bool(r[5]),
                    perm_withdraw=None if r[6] is None else bool(r[6]),
                )
                async for r in cur
            ]

    async def update_permissions(
        self, name: str, *, read: bool | None, trade: bool | None, withdraw: bool | None
    ) -> None:
        async with self._connect() as db:
            await db.execute(
                "UPDATE accounts SET perm_read=?, perm_trade=?, perm_withdraw=?, "
                "perm_checked_at=? WHERE name=?",
                (
                    None if read is None else int(read),
                    None if trade is None else int(trade),
                    None if withdraw is None else int(withdraw),
                    datetime.now(timezone.utc).isoformat(),
                    name,
                ),
            )
            await db.commit()

    async def get_credentials(self, name: str) -> ApiCredentials:
        async with self._connect() as db:
            cur = await db.execute(
                "SELECT key_version, nonce, ciphertext FROM accounts WHERE name=?", (name,)
            )
            row = await cur.fetchone()
        if row is None:
            raise KeyError(name)
        payload = json.loads(self._decrypt(int(row[0]), row[1], row[2]))
        return ApiCredentials(
            api_key=payload["api_key"],
            api_secret=payload["api_secret"],
            passphrase=payload.get("passphrase"),
        )

    async def delete_account(self, name: str) -> None:
        async with self._connect() as db:
            cur = await db.execute("DELETE FROM accounts WHERE name=?", (name,))
            await db.commit()
            if cur.rowcount == 0:
                raise KeyError(name)

    def _encrypt(self, plaintext: bytes) -> tuple[bytes, bytes]:
        nonce = secrets.token_bytes(12)
        ct = self._keys[self._active_version].encrypt(nonce, plaintext, None)
        return nonce, ct

    def _decrypt(self, key_version: int, nonce: bytes, ct: bytes) -> bytes:
        if key_version not in self._keys:
            raise RuntimeError(f"key_version {key_version} not loaded")
        return self._keys[key_version].decrypt(nonce, ct, None)
