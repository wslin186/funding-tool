"""ScrubbingFilter must:
  - replace API keys with a 6-char prefix + ellipsis
  - completely suppress api_secret values and any HMAC signature param
  - leave non-sensitive content untouched
"""

import logging

from funding_tool.infra.log import ScrubbingFilter, get_logger


def _capture(record_msg: str, *, args: tuple = ()) -> str:
    """Push a record through ScrubbingFilter, return the resulting message."""
    logger = logging.getLogger("test_scrub_" + record_msg[:6])
    logger.handlers.clear()
    logger.addFilter(ScrubbingFilter())
    logger.setLevel(logging.DEBUG)
    captured: list[str] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record.getMessage())

    logger.addHandler(_Capture())
    logger.debug(record_msg, *args)
    return captured[0]


def test_api_key_scrubbed_to_six_char_prefix():
    out = _capture("calling with X-MBX-APIKEY=ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    assert "ABCDEF" in out
    assert "GHIJKL" not in out
    assert "ABCDEFGH" not in out  # only first 6 retained
    assert "…" in out or "***" in out


def test_api_secret_value_never_appears():
    secret = "TopSecretApiSecret123456"
    out = _capture(f"using api_secret={secret}")
    assert secret not in out
    assert "api_secret" in out  # field name kept, value gone


def test_signature_query_param_scrubbed():
    out = _capture("GET /fapi/v1/income?timestamp=1&signature=deadbeefcafe1234")
    assert "deadbeefcafe1234" not in out


def test_unrelated_content_untouched():
    out = _capture("fetched 42 events for BTCUSDT")
    assert out == "fetched 42 events for BTCUSDT"


def test_get_logger_installs_filter_once():
    """Calling get_logger twice should not stack duplicate filters."""
    log1 = get_logger("funding_tool.test")
    n_filters_first = len(log1.filters)
    log2 = get_logger("funding_tool.test")
    assert log1 is log2
    assert len(log2.filters) == n_filters_first
    assert any(isinstance(f, ScrubbingFilter) for f in log2.filters)
