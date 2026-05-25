import json
from pathlib import Path

from funding_tool.web.audit import AuditLogger


def test_emits_jsonl(tmp_path: Path) -> None:
    log_file = tmp_path / "audit.jsonl"
    a = AuditLogger(log_file)
    a.log(action="login", ip="1.1.1.1", user="admin", result="ok")
    a.log(action="account_add", ip="1.1.1.1", user="admin",
          target="primary", result="ok")
    a.close()
    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 2
    e0 = json.loads(lines[0])
    assert e0["action"] == "login"
    assert e0["ip"] == "1.1.1.1"
    assert e0["user"] == "admin"
    assert e0["result"] == "ok"
    assert "ts" in e0


def test_failure_record_carries_error_code(tmp_path: Path) -> None:
    a = AuditLogger(tmp_path / "audit.jsonl")
    a.log(action="login", ip="1.1.1.1", user=None,
          result="fail", error_code="web_auth_required")
    a.close()
    e = json.loads((tmp_path / "audit.jsonl").read_text().strip())
    assert e["result"] == "fail"
    assert e["error_code"] == "web_auth_required"


def test_no_secret_fields_accepted(tmp_path: Path) -> None:
    """Schema rejects api_key/api_secret keys to prevent accidental logging."""
    import pytest
    a = AuditLogger(tmp_path / "audit.jsonl")
    with pytest.raises(ValueError):
        a.log(action="x", ip="1.1.1.1", user=None, result="ok",
              extras={"api_key": "leaked"})  # type: ignore[call-arg]
