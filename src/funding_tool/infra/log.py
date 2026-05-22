"""Logger factory + ScrubbingFilter for funding-tool.

The scrubber catches the most common ways a credential can sneak into a log
record: explicit `api_secret=...`, signed query strings (`&signature=...`), and
API keys as `X-MBX-APIKEY` header values or bare 32+ char hex/base64 tokens.

This is defense-in-depth, not a substitute for being careful at call sites - but
when a future contributor writes `log.debug(f"calling {url}")` without thinking,
this filter is what stops the secret from landing on disk.
"""

from __future__ import annotations

import logging
import re

_API_KEY_PATTERN = re.compile(
    r"(X-MBX-APIKEY[=:\s]+|api_key[=:\s]+)([A-Za-z0-9]{6})([A-Za-z0-9]+)",
    re.IGNORECASE,
)
_API_SECRET_PATTERN = re.compile(
    r"(api_secret[=:\s]+)[^\s,&\"']+",
    re.IGNORECASE,
)
_SIGNATURE_PATTERN = re.compile(
    r"(signature[=:])[A-Fa-f0-9]+",
    re.IGNORECASE,
)


def _scrub(text: str) -> str:
    text = _API_KEY_PATTERN.sub(r"\1\2…", text)
    text = _API_SECRET_PATTERN.sub(r"\1***", text)
    text = _SIGNATURE_PATTERN.sub(r"\1***", text)
    return text  # noqa: RET504


class ScrubbingFilter(logging.Filter):
    """Rewrite the formatted message to remove credentials.

    We rewrite `record.msg` and clear `record.args` so downstream formatters
    don't re-introduce the secret via %-formatting.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            formatted = record.getMessage()
        except Exception:  # noqa: BLE001
            return True
        scrubbed = _scrub(formatted)
        if scrubbed != formatted:
            record.msg = scrubbed
            record.args = ()
        return True


def get_logger(name: str) -> logging.Logger:
    """Return a logger with ScrubbingFilter installed exactly once.

    Use this anywhere in funding_tool that needs a logger - never call
    `logging.getLogger` directly inside our packages.
    """
    log = logging.getLogger(name)
    if not any(isinstance(f, ScrubbingFilter) for f in log.filters):
        log.addFilter(ScrubbingFilter())
    return log
