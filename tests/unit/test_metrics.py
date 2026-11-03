"""Metric formulas, commentary numbers, and module independence. No network."""

import ast
import inspect
from datetime import datetime
from pathlib import Path

from cm_agents.agents.metrics import (
    ChangeView,
    IncidentView,
    compute_metrics,
    find_candidates,
    proposed_template,
    unknown_numbers,
)
from cm_agents.data.teardown import _delete_change_children

ROOT = Path(__file__).resolve().parents[2]
_STAMP = "%Y-%m-%d %H:%M:%S"


def _at(text: str) -> datetime:
    return datetime.strptime(text, _STAMP)


def _change(
    sys_id: str,
    opened: str,
    *,
    change_type: str = "normal",
    state: str = "3",
    close_code: str = "successful",
    service: str = "SYN Online Store",
    environment: str = "prod",
    release: bool = False,
    summary: str = "SYN clear temporary export files",
    ci_class: str = "cmdb_ci_appl",
    group: str = "SYN Store DevOps",
    work_end: str = "2026-01-02 02:00:00",
    end_date: str = "2026-01-02 04:00:00",
) -> ChangeView:
    return ChangeView(
        sys_id=sys_id,
        opened_at=_at(opened),
        work_end=_at(work_end),
        end_date=_at(end_date),
        state=state,
        change_type=change_type,
        close_code=close_code,
        service=service,
        ci_environment=environment,
        ci_class=ci_class,
        assignment_group=group,
        short_description=summary,
        release=release,
    )


def test_stage_changes_are_not_prod_and_early_releases_stay_on_time() -> None:
    start = _at("2026-01-01 00:00:00")
    end = _at("2026-01-08 00:00:00")
    changes = [
        _change("prod", "2026-01-02 00:00:00"),
        _change("stage", "2026-01-02 00:00:00", environment="stage"),
        _change(
            "release-in",
            "2026-01-02 00:00:00",
            environment="",
            release=True,
            summary="SYN RELEASE SYN Online Store 2026.01.0",
        ),
        _change(
            "release-early",
            "2025-10-26 02:00:00",
            environment="",
            release=True,
            summary="SYN RELEASE SYN Online Store 2025.11.0",
            work_end="2025-11-07 08:00:00",
            end_date="2025-11-02 09:00:00",
        ),
    ]
    changes.append(_change("choice", "2026-01-03 00:00:00", environment="Production"))
    changes.append(_change("stored-test", "2026-01-03 00:00:00", environment="Test"))
    metrics = compute_metrics(changes, [], start, end)
    assert metrics["volume_by_service"] == {"SYN Online Store": 5}
    assert metrics["deployment_frequency_per_week"] == {"SYN Online Store": 3.0}
    assert metrics["release_on_time_pct"] == 50.0


def test_a_commentary_number_must_already_be_in_the_table() -> None:
    table = {"success_rate_pct": 93.9, "volume_by_type": {"normal": 10}}
    assert unknown_numbers("Success is 93.9 across 10 changes.", table) == []
    assert unknown_numbers("The hidden rate is 4.2.", table) == ["4.2"]


def test_candidates_propose_a_template_and_reject_a_failure() -> None:
    start = _at("2026-01-01 00:00:00")
    end = _at("2026-02-01 00:00:00")
    clean = [
        _change(f"ok-{index}", "2026-01-02 00:00:00", summary="SYN clear temporary export files")
        for index in range(10)
    ]
    failed = _change("bad", "2026-01-03 00:00:00", close_code="unsuccessful", summary="SYN other")
    caused = _change("caused", "2026-01-03 00:00:00", summary="SYN other two")
    incidents = [IncidentView(_at("2026-01-04 00:00:00"), _at("2026-01-04 04:00:00"), "caused")]
    found = find_candidates([*clean, failed, caused], incidents, start, end)
    assert len(found) == 1
    assert found[0]["signature"] == "syn clear temporary export files"
    assert found[0]["executions"] == 10
    assert found[0]["failures"] == 0
    assert found[0]["caused_incidents"] == 0
    assert found[0]["proposed_template"] == proposed_template(found[0]["signature"])
    assert found[0]["proposed_template"] == "SYN Standard clear temporary export files"


def test_metrics_and_the_generator_do_not_share_formulas() -> None:
    metrics_imports = _imports(ROOT / "cm_agents" / "agents" / "metrics.py")
    truth_imports = _imports(ROOT / "cm_agents" / "data" / "ground_truth.py")
    assert "cm_agents.rounding" in metrics_imports
    assert "cm_agents.rounding" in truth_imports
    assert "cm_agents.data.ground_truth" not in metrics_imports
    assert "cm_agents.data.generate" not in metrics_imports
    assert "cm_agents.agents.metrics" not in truth_imports


def test_metrics_do_not_read_change_tasks_and_teardown_deletes_them() -> None:
    source = (ROOT / "cm_agents" / "agents" / "metrics.py").read_text(encoding="utf-8")
    assert "change_task" not in source
    deletion = inspect.getsource(_delete_change_children)
    assert '"change_task"' in deletion


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found
