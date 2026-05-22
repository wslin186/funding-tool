from datetime import UTC, datetime, timezone

import pytest

from funding_tool.core.errors import ValidationError
from funding_tool.infra.time_util import from_ms, parse_user_datetime, to_ms


def test_parse_date_only_treated_as_utc_midnight():
    result = parse_user_datetime("2026-01-15")
    assert result == datetime(2026, 1, 15, tzinfo=UTC)


def test_parse_iso_with_z_suffix():
    result = parse_user_datetime("2026-01-15T08:30:00Z")
    assert result == datetime(2026, 1, 15, 8, 30, tzinfo=UTC)


def test_parse_iso_with_offset():
    result = parse_user_datetime("2026-01-15T08:30:00+02:00")
    expected = datetime(2026, 1, 15, 8, 30, tzinfo=timezone(__import__("datetime").timedelta(hours=2)))
    assert result.utcoffset() == expected.utcoffset()
    # And conversion to UTC works:
    assert result.astimezone(UTC) == datetime(2026, 1, 15, 6, 30, tzinfo=UTC)


def test_parse_naive_datetime_rejected():
    with pytest.raises(ValidationError, match="timezone"):
        parse_user_datetime("2026-01-15T08:30:00")


def test_parse_now_keyword():
    before = datetime.now(UTC)
    result = parse_user_datetime("now")
    after = datetime.now(UTC)
    assert before <= result <= after


def test_to_ms_and_back():
    dt = datetime(2026, 1, 15, 8, 30, tzinfo=UTC)
    ms = to_ms(dt)
    assert ms == int(dt.timestamp() * 1000)
    assert from_ms(ms) == dt


def test_to_ms_rejects_naive():
    with pytest.raises(ValidationError, match="timezone"):
        to_ms(datetime(2026, 1, 15))
