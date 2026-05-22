# funding-tool

A Python CLI for computing Binance USDT-M perpetual **funding rate P&L** — both
hypothetical backtests and real account history.

## Features

- **Backtest** (feature A): pick symbol + side + start time + position-sizing mode (BASE / QUOTE / RATE_ONLY) and compute what funding would have cost or paid you.
- **Account history** (feature B): query your real funding-fee history via Binance API and summarize by symbol / by month.
- **Multi-account**: keyring-backed credential store with named accounts (no plaintext secrets in YAML).
- **Local cache**: SQLite cache for immutable funding-rate history — first query is slow, subsequent queries are instant.
- **Extensible**: layered architecture; adding OKX or Bybit means implementing one `ExchangeProtocol` class.

## Installation

```bash
git clone <repo>
cd funding-tool
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Quick start

### Backtest a 1-BTC long position

```bash
funding-tool backtest \
    --symbol BTCUSDT --side LONG \
    --start 2026-01-01 --end now \
    --size-mode BASE --size 1
```

### Pure funding-rate P&L (RATE_ONLY mode)

```bash
funding-tool backtest \
    --symbol BTCUSDT --side LONG \
    --start 2026-01-01 \
    --size-mode RATE_ONLY
```

### Register an account and query its history

```bash
funding-tool account add --name my-main
funding-tool history --account my-main --start 2026-01-01 --by-symbol --by-month
```

## Security notes

- `api_key` AND `api_secret` are stored in the system keyring (macOS Keychain / Linux Secret Service / Windows Credential Manager). The YAML config only holds references.
- When you register an account, the tool verifies that the API key has Futures **read** permission and warns if it has trading or withdrawal permissions enabled.
- If your environment has no keyring backend (e.g., headless Linux without DBus), the tool will refuse to silently fall back — it asks for explicit confirmation before writing plaintext to a 0600-permissioned YAML.

For maximum safety, create an API key on Binance with **only "Enable Futures" read permission** and IP whitelisting.

## Configuration paths

| Purpose | Path |
|---|---|
| Account YAML | `~/.config/funding-tool/accounts.yaml` (`XDG_CONFIG_HOME` respected) |
| Cache SQLite | `~/.local/share/funding-tool/cache.sqlite` (`XDG_DATA_HOME` respected) |

## Time handling

All internal datetimes are tz-aware UTC. Accepted input formats:

- `YYYY-MM-DD` (interpreted as UTC midnight; the CLI prints a notice)
- ISO-8601 with explicit timezone, e.g. `2026-01-15T08:30:00Z` or `2026-01-15T08:30:00+02:00`
- `now` (only at the CLI/UI layer; never reaches the service layer)

Naive datetime strings (no timezone suffix) are **rejected** — you must add `Z` or an offset.

## Architecture

```
CLI (typer)
  └── Service layer (pure functions: backtest, account_history, account_store)
        └── ExchangeProtocol (abstract)
              └── BinanceUsdmExchange (impl)
                    └── Infra: httpx, SQLite cache, keyring
```

The service layer is IO-free and pure-parametric, which is why the planned Web UI can be a thin FastAPI wrapper around it. See `docs/superpowers/specs/2026-05-22-funding-tool/` for the full design spec.

## Development

```bash
pytest                       # unit tests
pytest -m integration        # live integration tests (hit Binance public API)
ruff check .                 # lint
mypy src                     # type check
```

Conventions:
- All money uses `Decimal`. The `float(...)` constructor is **banned** in `src/funding_tool/core/`.
- TDD: write the failing test first, then the implementation.
- Conventional commits: `feat:`, `fix:`, `test:`, `refactor:`, `chore:`.
