"""Smoke test: web package importable and routes namespace exists."""


def test_web_package_imports() -> None:
    import funding_tool.web  # noqa: F401
    import funding_tool.web.routes  # noqa: F401
