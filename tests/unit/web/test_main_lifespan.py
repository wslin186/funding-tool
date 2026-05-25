import os
import pytest
from pathlib import Path

from funding_tool.web.main import _load_master_key_from_credentials


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
