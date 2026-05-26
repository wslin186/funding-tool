import os
from pathlib import Path

import pytest

from funding_tool.core.cache import SqliteFundingRateCache
from funding_tool.core.exchanges.binance_usdm import BinanceUsdmExchange
from funding_tool.core.models import ApiCredentials
from funding_tool.web.main import (
    _load_master_key_from_credentials,
    _make_exchange_factory,
)


def test_load_master_key_reads_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cred_dir = tmp_path / "creds"
    cred_dir.mkdir()
    key = os.urandom(32)
    (cred_dir / "master_key").write_bytes(key)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(cred_dir))
    active, prev = _load_master_key_from_credentials()
    assert active == key
    assert prev is None


def test_load_master_key_with_prev(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cred_dir = tmp_path / "creds"
    cred_dir.mkdir()
    k1 = os.urandom(32)
    k2 = os.urandom(32)
    (cred_dir / "master_key").write_bytes(k1)
    (cred_dir / "master_key_prev").write_bytes(k2)
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(cred_dir))
    active, prev = _load_master_key_from_credentials()
    assert active == k1
    assert prev == k2


def test_load_master_key_wrong_length_panics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cred_dir = tmp_path / "creds"
    cred_dir.mkdir()
    (cred_dir / "master_key").write_bytes(b"short")
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(cred_dir))
    with pytest.raises(RuntimeError, match="32 bytes"):
        _load_master_key_from_credentials()


# Regression: the production factory previously built
# `BinanceUsdmExchange(credentials=...)`, which doesn't match the constructor
# (it takes a SqliteFundingRateCache). The first route to call factory(...)
# would have TypeError'd in production. The factory's `creds` arg is kept for
# call-site compatibility (accounts/history pass creds; backtest/meta don't);
# credentials reach the exchange via per-method calls, not the constructor.
def test_factory_returns_exchange_with_no_args(tmp_path: Path) -> None:
    cache = SqliteFundingRateCache(tmp_path / "cache.sqlite")
    factory = _make_exchange_factory(cache)
    ex = factory()
    assert isinstance(ex, BinanceUsdmExchange)


def test_factory_accepts_positional_and_kwarg_creds(tmp_path: Path) -> None:
    cache = SqliteFundingRateCache(tmp_path / "cache.sqlite")
    factory = _make_exchange_factory(cache)
    creds = ApiCredentials(api_key="k" * 16, api_secret="s" * 16)
    assert isinstance(factory(creds), BinanceUsdmExchange)
    assert isinstance(factory(creds=creds), BinanceUsdmExchange)
