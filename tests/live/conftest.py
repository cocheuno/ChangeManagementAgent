import os
from pathlib import Path

import pytest

os.environ.setdefault("CM_AGENTS_RUN", "phase2-gate")

_HERE = Path(__file__).parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Every test in this directory needs the PDI or the LLM."""
    for item in items:
        if _HERE in item.path.parents:
            item.add_marker(pytest.mark.live)
