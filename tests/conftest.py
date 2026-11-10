"""Keep the default pytest run offline.

Tests under tests/live need the PDI or the LLM. They are marked `live`.
When no `-m` expression is given, those tests are not collected. `pytest -m live`
and `pytest -m "not live"` then select the two suites. Do not put `-m` in
addopts: pytest ANDs that with a later `-m`, and `-m live` would match nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    if _markexpr(config):
        return None
    if "live" in collection_path.parts:
        return True
    return None


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if "live" in Path(str(item.path)).parts:
            item.add_marker(pytest.mark.live)
    if _markexpr(config):
        return
    items[:] = [item for item in items if "live" not in Path(str(item.path)).parts]


def _markexpr(config: pytest.Config) -> str:
    return str(getattr(config.option, "markexpr", "") or "")
