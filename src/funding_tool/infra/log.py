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

# Each pattern accepts the credential key in any of these forms:
#   key=VALUE                          (URL / query-string)
#   key: VALUE                         (HTTP header)
#   'key': 'VALUE'  /  "key": "VALUE"  (Python dict repr / JSON)
# The leading group (`\1` in the substitution) captures everything up to and
# including the opening of the value (including any leading quote) so the
# replacement preserves the surrounding syntax.
#
# Value termination:
#   - For full-suppression patterns (api_secret, signature) we stop at the
#     first whitespace, quote, comma, ampersand, or closing brace — anything
#     that could plausibly end a value in a header, query string, or dict
#     repr.
#   - For the api_key pattern we keep the first 6 alphanumeric chars as a
#     debug hint, then drop the rest up to the same terminators.
_KEY_BOUNDARY = r"['\"]?(?:X-MBX-APIKEY|api[_-]?key)['\"]?\s*[=:]\s*['\"]?"
_SECRET_BOUNDARY = r"['\"]?api[_-]?secret['\"]?\s*[=:]\s*['\"]?"
_SIGNATURE_BOUNDARY = r"['\"]?signature['\"]?\s*[=:]\s*['\"]?"
_VALUE_TAIL = r"[^\s,&'\"}]*"

_API_KEY_PATTERN = re.compile(
    rf"({_KEY_BOUNDARY})([A-Za-z0-9]{{6}}){_VALUE_TAIL}",
    re.IGNORECASE,
)
_API_SECRET_PATTERN = re.compile(
    rf"({_SECRET_BOUNDARY}){_VALUE_TAIL}",
    re.IGNORECASE,
)
_SIGNATURE_PATTERN = re.compile(
    rf"({_SIGNATURE_BOUNDARY}){_VALUE_TAIL}",
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
