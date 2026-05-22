"""Enforces the 'no float() constructor in core/' rule from the spec.

Decimal money values lose precision the moment they pass through float().
We catch any reintroduction here so reviewers don't have to remember.
"""

from pathlib import Path


def test_no_float_constructor_in_core() -> None:
    core_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "src" / "funding_tool" / "core"
    )
    offenders: list[str] = []
    for py in core_dir.rglob("*.py"):
        for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if "float(" in line:
                offenders.append(f"{py}:{lineno}: {line.rstrip()}")
    assert not offenders, (
        "float() is banned in src/funding_tool/core/ (use Decimal(str(...))):\n"
        + "\n".join(offenders)
    )
