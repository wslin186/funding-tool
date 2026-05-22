"""AccountStore unit tests. Uses an in-memory fake keyring to avoid hitting the OS."""

from pathlib import Path

import pytest

from funding_tool.core.account_store import (
    AccountStore,
    PlaintextFallbackRequired,
)
from funding_tool.core.errors import ConfigError
from funding_tool.core.models import ApiCredentials


class FakeKeyring:
    """In-memory stand-in for the `keyring` module. Mirrors the subset we use."""

    def __init__(self, *, available: bool = True) -> None:
        self._available = available
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        if not self._available:
            raise RuntimeError("no keyring backend")
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, value: str) -> None:
        if not self._available:
            raise RuntimeError("no keyring backend")
        self._store[(service, username)] = value

    def delete_password(self, service: str, username: str) -> None:
        if not self._available:
            raise RuntimeError("no keyring backend")
        self._store.pop((service, username), None)


@pytest.fixture
def store(tmp_path: Path) -> AccountStore:
    return AccountStore(config_path=tmp_path / "accounts.yaml", keyring=FakeKeyring())


def test_add_and_list_account(store: AccountStore) -> None:
    store.add(
        name="my-main",
        exchange="binance_usdm",
        credentials=ApiCredentials(api_key="K1", api_secret="S1"),
        verified=True,
    )
    accounts = store.list_accounts()
    assert [a.name for a in accounts] == ["my-main"]
    assert accounts[0].exchange == "binance_usdm"
    assert accounts[0].permissions_verified_at is not None


def test_get_credentials(store: AccountStore) -> None:
    store.add(
        name="my-main",
        exchange="binance_usdm",
        credentials=ApiCredentials(api_key="K1", api_secret="S1"),
    )
    creds = store.get_credentials("my-main")
    assert creds.api_key == "K1"
    assert creds.api_secret == "S1"


def test_yaml_never_contains_plaintext_secrets(store: AccountStore, tmp_path: Path) -> None:
    store.add(
        name="my-main",
        exchange="binance_usdm",
        credentials=ApiCredentials(api_key="K1", api_secret="S1"),
    )
    text = (tmp_path / "accounts.yaml").read_text()
    assert "K1" not in text
    assert "S1" not in text
    assert "keyring:" in text


def test_default_account(store: AccountStore) -> None:
    store.add(name="a", exchange="binance_usdm",
              credentials=ApiCredentials(api_key="K1", api_secret="S1"))
    store.add(name="b", exchange="binance_usdm",
              credentials=ApiCredentials(api_key="K2", api_secret="S2"))
    # First added becomes default automatically.
    assert store.get_default_name() == "a"
    store.set_default("b")
    assert store.get_default_name() == "b"


def test_remove_account_clears_keyring(tmp_path: Path) -> None:
    kr = FakeKeyring()
    store = AccountStore(config_path=tmp_path / "accounts.yaml", keyring=kr)
    store.add(name="a", exchange="binance_usdm",
              credentials=ApiCredentials(api_key="K1", api_secret="S1"))
    store.remove("a")
    assert store.list_accounts() == []
    assert kr._store == {}


def test_remove_unknown_account_raises(store: AccountStore) -> None:
    with pytest.raises(ConfigError, match="not found"):
        store.remove("nope")


def test_yaml_file_has_0600_permissions(store: AccountStore, tmp_path: Path) -> None:
    store.add(name="a", exchange="binance_usdm",
              credentials=ApiCredentials(api_key="K1", api_secret="S1"))
    # 0600 = -rw-------
    mode = (tmp_path / "accounts.yaml").stat().st_mode & 0o777
    assert mode == 0o600


def test_no_keyring_backend_raises_plaintext_fallback_required(tmp_path: Path) -> None:
    """If keyring is unavailable, the store must raise — never silently store plaintext."""
    store = AccountStore(
        config_path=tmp_path / "accounts.yaml",
        keyring=FakeKeyring(available=False),
    )
    with pytest.raises(PlaintextFallbackRequired):
        store.add(name="a", exchange="binance_usdm",
                  credentials=ApiCredentials(api_key="K1", api_secret="S1"))


def test_explicit_plaintext_fallback(tmp_path: Path) -> None:
    """Caller can opt into plaintext storage after seeing PlaintextFallbackRequired."""
    store = AccountStore(
        config_path=tmp_path / "accounts.yaml",
        keyring=FakeKeyring(available=False),
    )
    store.add(
        name="a", exchange="binance_usdm",
        credentials=ApiCredentials(api_key="K1", api_secret="S1"),
        allow_plaintext=True,
    )
    text = (tmp_path / "accounts.yaml").read_text()
    assert "K1" in text and "S1" in text
    assert "_plaintext_warning" in text
    # Read back works:
    assert store.get_credentials("a").api_key == "K1"


def test_load_existing_yaml(tmp_path: Path) -> None:
    """A second store instance on the same yaml file sees previously added accounts."""
    kr = FakeKeyring()
    s1 = AccountStore(config_path=tmp_path / "accounts.yaml", keyring=kr)
    s1.add(name="a", exchange="binance_usdm",
           credentials=ApiCredentials(api_key="K1", api_secret="S1"))
    s2 = AccountStore(config_path=tmp_path / "accounts.yaml", keyring=kr)
    assert [a.name for a in s2.list_accounts()] == ["a"]
    assert s2.get_credentials("a").api_key == "K1"


def test_resolve_credentials_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """resolve_credentials honors: cli > env > named > default."""
    from funding_tool.core.account_store import resolve_credentials

    kr = FakeKeyring()
    store = AccountStore(config_path=tmp_path / "accounts.yaml", keyring=kr)
    store.add(name="default-acc", exchange="binance_usdm",
              credentials=ApiCredentials(api_key="DK", api_secret="DS"))
    store.add(name="other", exchange="binance_usdm",
              credentials=ApiCredentials(api_key="OK", api_secret="OS"))

    # CLI flags win:
    c = resolve_credentials(
        store, cli_api_key="CK", cli_api_secret="CS",
        env={"BINANCE_API_KEY": "EK", "BINANCE_API_SECRET": "ES"},
        account_name="other",
    )
    assert c.api_key == "CK"

    # Env beats named account:
    c = resolve_credentials(
        store, cli_api_key=None, cli_api_secret=None,
        env={"BINANCE_API_KEY": "EK", "BINANCE_API_SECRET": "ES"},
        account_name="other",
    )
    assert c.api_key == "EK"

    # Named account beats default:
    c = resolve_credentials(
        store, cli_api_key=None, cli_api_secret=None,
        env={}, account_name="other",
    )
    assert c.api_key == "OK"

    # Falls back to default:
    c = resolve_credentials(store, cli_api_key=None, cli_api_secret=None,
                            env={}, account_name=None)
    assert c.api_key == "DK"
