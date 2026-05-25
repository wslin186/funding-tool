"""Mirror of core's no-float rule, applied to src/funding_tool/web/."""
from pathlib import Path


def test_no_float_constructor_in_web() -> None:
    web_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "src" / "funding_tool" / "web"
    )
    offenders: list[str] = []
    for py in web_dir.rglob("*.py"):
        for lineno, line in enumerate(py.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if "float(" in line:
                offenders.append(f"{py}:{lineno}: {line.rstrip()}")
    assert not offenders, (
        "float() is banned in src/funding_tool/web/ (use Decimal(str(...))):\n"
        + "\n".join(offenders)
    )
