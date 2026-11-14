"""Run one scenario, or S01 through S10, against the seeded PDI.

`all` runs S01, the closed S02 outcome, then S03 through S09. S10 is the
second half of the S09 test, so it is not launched again. The S02 file that
stops at go/no-go stays a live test and is not part of `all`: running it
beside the close test would put two changes on syn-hr-portal.

Each scenario is a pytest file marked `live`. Scenario rows are removed
after a passing file so the next file does not see them. A failure leaves
those rows in place.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable

from cm_agents.data.teardown import remove_scenario_records
from cm_agents.deploy.simulator import describe_state
from cm_agents.settings import Settings, repo_root

SCENARIO_FILES = {
    "S01": "tests/live/test_s01.py",
    "S02": "tests/live/test_s02_close.py",
    "S03": "tests/live/test_s03.py",
    "S04": "tests/live/test_s04.py",
    "S05": "tests/live/test_s05.py",
    "S06": "tests/live/test_s06.py",
    "S07": "tests/live/test_s07.py",
    "S08": "tests/live/test_s08.py",
    "S09": "tests/live/test_s09.py",
    "S10": "tests/live/test_s09.py",
}
ALL = ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08", "S09")


class ScenarioError(Exception):
    """The scenario name is not S01 through S10 or all."""


def scenario_names(name: str) -> list[str]:
    token = name.strip()
    if token == "all":
        return list(ALL)
    if token not in SCENARIO_FILES:
        raise ScenarioError(f"unknown scenario {name}")
    return [token]


def run_scenarios(
    settings: Settings,
    name: str,
    *,
    runner: Callable[[str], int] | None = None,
) -> int:
    """Print simulator state, run the named scenarios, and clean up after each."""
    names = scenario_names(name)
    chosen = runner or _pytest
    print(f"simulator state: {describe_state()}", flush=True)
    for scenario in names:
        print(f"scenario {scenario}", flush=True)
        code = chosen(SCENARIO_FILES[scenario])
        if code != 0:
            print(f"scenario {scenario} failed", flush=True)
            return code
        remove_scenario_records(settings)
    return 0


def _pytest(path: str) -> int:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "live", path, "-s", "--tb=short"],
        cwd=repo_root(),
        check=False,
    )
    return int(completed.returncode)
