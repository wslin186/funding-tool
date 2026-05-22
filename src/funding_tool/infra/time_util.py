"""Datetime parsing and conversion. All returned datetimes are tz-aware (UTC or explicit offset)."""

from datetime import UTC, datetime

from funding_tool.core.errors import ValidationError

_DATE_ONLY_LEN = 10  # "YYYY-MM-DD"


def parse_user_datetime(value: str) -> datetime:
    """Parse a CLI-supplied date or datetime string into a tz-aware UTC datetime.

    Rules:
      - "now" → current UTC time
      - "YYYY-MM-DD" → that date at UTC midnight
      - "YYYY-MM-DDTHH:MM:SS<Z|±HH:MM>" → ISO-8601 with explicit timezone
      - Naive datetimes (no tz suffix) are rejected.
    """
    value = value.strip()
    if value.lower() == "now":
        return datetime.now(UTC)

    if len(value) == _DATE_ONLY_LEN:
        try:
            d = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as exc:
            raise ValidationError(f"invalid date: {value!r}") from exc
        return d.replace(tzinfo=UTC)

    try:
        dt = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(f"invalid datetime: {value!r}") from exc

    if dt.tzinfo is None:
        raise ValidationError(
            f"datetime {value!r} has no timezone; append 'Z' or '±HH:MM'"
        )
    return dt


def to_ms(dt: datetime) -> int:
    """Convert tz-aware datetime to unix milliseconds. Rejects naive datetimes."""
    if dt.tzinfo is None:
        raise ValidationError("datetime must be timezone-aware")
    return int(dt.timestamp() * 1000)


def from_ms(ms: int) -> datetime:
    """Convert unix milliseconds to UTC datetime."""
    return datetime.fromtimestamp(ms / 1000, tz=UTC)
