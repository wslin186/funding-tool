"""Integration-test fixtures.

The integration suite shells out to the CLI and constructs the production
exchange factory, both of which resolve their cache path via
``XDG_DATA_HOME`` (falling back to ``~/.local/share``). Without isolation,
running ``pytest -m integration`` would mutate the developer's real
``~/.local/share/funding-tool/cache.sqlite`` file.

The fixture below redirects ``XDG_DATA_HOME`` to a temp directory for the
whole integration session, so all writes land in pytest-managed scratch
space and the user's real cache is left untouched.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True, scope="session")
def _isolate_xdg_data_home(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """Redirect ``XDG_DATA_HOME`` to a session-scoped tmp dir.

    Session scope keeps the same cache directory across all integration
    tests (efficient — paginated fetches can reuse cached rows), while
    still guaranteeing it lives outside the user's real XDG data dir.

    ``pytest.MonkeyPatch.context()`` is required because the built-in
    ``monkeypatch`` fixture is function-scoped and cannot be used at
    session scope.
    """
    xdg_dir = tmp_path_factory.mktemp("xdg_data")
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("XDG_DATA_HOME", str(xdg_dir))
        yield
