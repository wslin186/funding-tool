"""SQLite-backed cache for immutable funding rate history."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from funding_tool.core.errors import CacheCorruptionError
from funding_tool.core.models import FundingEvent
from funding_tool.infra.time_util import from_ms, to_ms

_SCHEMA = """
CREATE TABLE IF NOT EXISTS funding_rates (
    exchange     TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    funding_ms   INTEGER NOT NULL,
    rate         TEXT NOT NULL,
    mark_price   TEXT NOT NULL,
    interval_h   INTEGER NOT NULL,
    fetched_at   INTEGER NOT NULL,
    PRIMARY KEY (exchange, symbol, funding_ms)
);
"""


class SqliteFundingRateCache:
    """File-backed cache. Synchronous SQLite wrapped in async methods for protocol parity."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    async def put(self, exchange: str, symbol: str, events: list[FundingEvent]) -> None:
        if not events:
            return
        rows = [
            (
                exchange, symbol, to_ms(ev.timestamp),
                str(ev.rate), str(ev.mark_price), ev.interval_hours,
                to_ms(datetime.now(ev.timestamp.tzinfo)),
            )
            for ev in events
        ]
        with self._conn() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO funding_rates "
                "(exchange, symbol, funding_ms, rate, mark_price, interval_h, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

    async def get(
        self, exchange: str, symbol: str, start: datetime, end: datetime
    ) -> list[FundingEvent]:
        start_ms, end_ms = to_ms(start), to_ms(end)
        with self._conn() as conn:
            cur = conn.execute(
                "SELECT funding_ms, rate, mark_price, interval_h "
                "FROM funding_rates "
                "WHERE exchange = ? AND symbol = ? AND funding_ms >= ? AND funding_ms <= ? "
                "ORDER BY funding_ms ASC",
                (exchange, symbol, start_ms, end_ms),
            )
            return [
                FundingEvent(
                    timestamp=from_ms(funding_ms),
                    symbol=symbol,
                    rate=Decimal(rate),
                    mark_price=Decimal(mark_price),
                    interval_hours=interval_h,
                )
                for (funding_ms, rate, mark_price, interval_h) in cur.fetchall()
            ]

    async def missing_ranges(
        self, exchange: str, symbol: str, start: datetime, end: datetime
    ) -> list[tuple[datetime, datetime]]:
        """Compute sub-ranges of [start, end] not covered by cache.

        Binance funding timestamps drift by milliseconds across consecutive
        events (e.g. one at ``:00:00.007Z``, the next at ``:00:00.013Z``).
        A gap is only reported when the delta is large enough to contain at
        least one missing funding event — concretely, when the delta is
        within roughly one full ``interval_hours`` we treat the boundary as
        contiguous and emit no gap. The tolerance threshold used is
        ``1.5 * interval_hours``: well above any realistic ms-level jitter,
        comfortably below a true missing event (≥ 2 intervals apart).

        Returns:
          - leading gap (start, first_cached.ts) when start precedes the
            first cached event by at least roughly one interval
          - interior gap (prev.ts + interval, next.ts) when the delta
            between adjacent cached events exceeds ~1 interval
          - trailing gap (last_cached.ts + interval, end) when end follows
            the last cached event by more than ~1 interval

        Empty cache in window → single gap (start, end).
        """
        cached = await self.get(exchange, symbol, start, end)
        if not cached:
            return [(start, end)]

        gaps: list[tuple[datetime, datetime]] = []

        # All three branches use the same strict-greater-than tolerance check
        # against ``1.5 * interval_hours`` so the boundary at delta == 1.5*interval
        # is treated identically as "no gap" (matches the docstring's "exceeds").
        # Leading gap — only report when `start` precedes the first cached
        # event by more than ~1 interval (i.e. there's room for a missing
        # funding event between them). Sub-interval drift is jitter, not a gap.
        first = cached[0]
        leading_tolerance = (timedelta(hours=first.interval_hours) * 3) // 2
        if first.timestamp - start > leading_tolerance:
            gaps.append((start, first.timestamp))

        # Interior gaps — adjacent cached events whose delta is too large to
        # be explained by ms-level jitter on a single interval boundary.
        for prev, nxt in zip(cached, cached[1:], strict=False):
            interval = timedelta(hours=prev.interval_hours)
            interior_tolerance = (interval * 3) // 2
            if nxt.timestamp - prev.timestamp > interior_tolerance:
                gaps.append((prev.timestamp + interval, nxt.timestamp))

        # Trailing gap — symmetric to leading: only report when `end` follows
        # the last cached event by more than ~1 interval.
        last = cached[-1]
        next_after_last = last.timestamp + timedelta(hours=last.interval_hours)
        trailing_tolerance = (timedelta(hours=last.interval_hours) * 3) // 2
        if end - last.timestamp > trailing_tolerance:
            gaps.append((next_after_last, end))

        return gaps

    # --- methods used by CLI `cache info` / `cache clear` (see Task 17) ---

    def stats(self) -> list[dict[str, object]]:
        """Per-(exchange, symbol) row count + min/max funding_ms (as ISO dates)."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT exchange, symbol, COUNT(*) AS rows,
                       MIN(funding_ms) AS min_ms, MAX(funding_ms) AS max_ms
                FROM funding_rates
                GROUP BY exchange, symbol
                ORDER BY exchange, symbol
                """
            ).fetchall()
        out: list[dict[str, object]] = []
        for r in rows:
            first = from_ms(r["min_ms"]).date().isoformat() if r["min_ms"] is not None else None
            last = from_ms(r["max_ms"]).date().isoformat() if r["max_ms"] is not None else None
            out.append({
                "exchange": r["exchange"], "symbol": r["symbol"],
                "rows": r["rows"], "first": first, "last": last,
            })
        return out

    def clear(self, *, symbol: str | None = None) -> int:
        """Delete all rows or only those for one symbol. Returns count deleted."""
        with self._conn() as conn:
            if symbol:
                cur = conn.execute(
                    "DELETE FROM funding_rates WHERE symbol = ?", (symbol,),
                )
            else:
                cur = conn.execute("DELETE FROM funding_rates")
            return cur.rowcount

    def check_integrity(self) -> None:
        """Run SQLite's `PRAGMA integrity_check`. Raises `CacheCorruptionError` on
        any failure (corrupt file, unreadable, or integrity-check error string)."""
        try:
            with self._conn() as conn:
                row = conn.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.DatabaseError as exc:
            raise CacheCorruptionError(
                f"cache at {self._db_path} is unreadable: {exc}"
            ) from exc
        if row is None or row[0] != "ok":
            raise CacheCorruptionError(
                f"cache at {self._db_path} failed integrity_check: "
                f"{row[0] if row else 'no result'}"
            )
