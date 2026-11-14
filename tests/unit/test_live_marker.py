"""The live marker splits the suite. Collection does not call the PDI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _collect(*args: str) -> str:
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def test_live_marker_splits_offline_and_live_suites() -> None:
    default = _collect()
    offline = _collect("-m", "not live")
    live = _collect("-m", "live")
    assert "test_s01.py" not in default
    assert "test_s01.py" not in offline
    assert "test_s01.py" in live
    assert "test_plan_quality.py" in live
    assert "tests/unit" in default or "test_release.py" in default
