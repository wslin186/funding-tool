import os
import pytest
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidTag

from funding_tool.core.models import ApiCredentials
from funding_tool.web.secret_store import SecretStore


@pytest.fixture
def master_key() -> bytes:
    return os.urandom(32)


@pytest.fixture
async def store(tmp_path: Path, master_key: bytes) -> SecretStore:
    s = SecretStore(tmp_path / "secrets.sqlite", master_key=master_key)
    await s.init_schema()
    return s


async def test_add_and_get_credentials_roundtrip(store: SecretStore) -> None:
    creds = ApiCredentials(api_key="ABCDEF123456", api_secret="topsecret")
    await store.add_account("primary", "main account", creds)
    got = await store.get_credentials("primary")
    assert got.api_key == "ABCDEF123456"
    assert got.api_secret == "topsecret"


async def test_list_accounts_returns_no_secrets(store: SecretStore) -> None:
    creds = ApiCredentials(api_key="ABCDEF123456", api_secret="topsecret")
    await store.add_account("primary", "main", creds)
    recs = await store.list_accounts()
    assert len(recs) == 1
    assert recs[0].name == "primary"
    assert recs[0].label == "main"
    assert recs[0].key_first6 == "ABCDEF"
    assert not any(f.name in ("api_key", "api_secret")
                   for f in recs[0].__dataclass_fields__.values())


async def test_delete_account(store: SecretStore) -> None:
    creds = ApiCredentials(api_key="K", api_secret="S")
    await store.add_account("a", "", creds)
    await store.delete_account("a")
    assert await store.list_accounts() == []


async def test_wrong_master_key_fails_to_decrypt(tmp_path: Path) -> None:
    k1, k2 = os.urandom(32), os.urandom(32)
    s1 = SecretStore(tmp_path / "db.sqlite", master_key=k1)
    await s1.init_schema()
    await s1.add_account("a", "", ApiCredentials("K", "S"))
    s2 = SecretStore(tmp_path / "db.sqlite", master_key=k2)
    with pytest.raises(InvalidTag):
        await s2.verify_canary()


async def test_canary_passes_with_correct_key(store: SecretStore) -> None:
    await store.verify_canary()


async def test_delete_missing_account_raises(store: SecretStore) -> None:
    with pytest.raises(KeyError):
        await store.delete_account("nonexistent")


async def test_duplicate_name_rejected(store: SecretStore) -> None:
    await store.add_account("a", "", ApiCredentials("K", "S"))
    with pytest.raises(ValueError):
        await store.add_account("a", "", ApiCredentials("K2", "S2"))
