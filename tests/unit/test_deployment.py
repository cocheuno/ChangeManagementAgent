"""Deployment preconditions. No network and no model."""

from datetime import datetime
from typing import Any

from cm_agents.agents.context import AgentContext, activate, reset
from cm_agents.agents.deployment import _precondition, run_deployment
from cm_agents.clock import pin
from cm_agents.data.import_time import UTC
from cm_agents.deploy.simulator import RedeployBlocked

SATURDAY_START = "2026-11-08 03:00:00"
SATURDAY_END = "2026-11-08 05:00:00"
SATURDAY_INSIDE = datetime(2026, 11, 8, 3, 30, tzinfo=UTC)
TUESDAY_START = "2026-11-03 15:00:00"
TUESDAY_END = "2026-11-03 17:00:00"
TUESDAY_INSIDE = datetime(2026, 11, 3, 15, 30, tzinfo=UTC)


def test_normal_change_without_a_go_is_blocked() -> None:
    reason = _precondition(
        _state("normal"),
        _record("-2", SATURDAY_START, SATURDAY_END),
    )
    assert reason == "normal change has no go decision"


def test_emergency_change_does_not_need_a_go() -> None:
    pin(SATURDAY_INSIDE)
    try:
        reason = _precondition(
            _state("emergency"),
            _record("-2", SATURDAY_START, SATURDAY_END),
        )
    finally:
        pin(None)
    assert reason == ""


def test_a_change_that_is_not_scheduled_is_blocked() -> None:
    reason = _precondition(
        _state("normal", decision="go"),
        _record("-5", SATURDAY_START, SATURDAY_END),
    )
    assert reason == "change is not Scheduled"


def test_a_missing_window_is_blocked() -> None:
    reason = _precondition(_state("normal", decision="go"), _record("-2", "", ""))
    assert reason == "approved window is missing"


def test_a_clock_outside_the_window_is_blocked() -> None:
    pin(datetime(2026, 11, 8, 2, 0, tzinfo=UTC))
    try:
        reason = _precondition(
            _state("normal", decision="go"),
            _record("-2", SATURDAY_START, SATURDAY_END),
        )
    finally:
        pin(None)
    assert reason == "clock is outside the approved window"


def test_a_standard_change_outside_maintenance_is_blocked() -> None:
    pin(TUESDAY_INSIDE)
    try:
        reason = _precondition(
            _state("standard", tier=1),
            _record("-2", TUESDAY_START, TUESDAY_END),
        )
    finally:
        pin(None)
    assert reason == "standard change is outside the policy maintenance window"


def test_a_normal_change_outside_maintenance_is_not_blocked() -> None:
    pin(TUESDAY_INSIDE)
    try:
        reason = _precondition(
            _state("normal", decision="go"),
            _record("-2", TUESDAY_START, TUESDAY_END),
        )
    finally:
        pin(None)
    assert reason == ""


def test_a_standard_change_inside_the_saturday_window_is_allowed() -> None:
    pin(SATURDAY_INSIDE)
    try:
        reason = _precondition(
            _state("standard", tier=1),
            _record("-2", SATURDAY_START, SATURDAY_END),
        )
    finally:
        pin(None)
    assert reason == ""


def test_a_prod_failure_is_not_retried(monkeypatch, tmp_path) -> None:
    calls = {"deploy": 0, "rollback": 0}

    def deploy(*_args, **_kwargs):
        calls["deploy"] += 1
        raise RedeployBlocked("PROD deploy blocked for syn-ful-api after a recorded failure")

    def rollback(*_args, **_kwargs):
        calls["rollback"] += 1
        raise AssertionError("rollback ran after a blocked redeploy")

    monkeypatch.setattr("cm_agents.agents.deployment.run_deploy", deploy)
    monkeypatch.setattr("cm_agents.agents.deployment.run_rollback", rollback)
    monkeypatch.setattr("cm_agents.agents.deployment.default_path", lambda: tmp_path / "sim.json")
    monkeypatch.setattr("cm_agents.agents.deployment.record_audit", lambda **_kwargs: None)
    monkeypatch.setattr("cm_agents.agents.deployment.write_note", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("cm_agents.servicenow.changes.journal", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "cm_agents.agents.deployment.read_change",
        lambda *_args, **_kwargs: _record("-2", SATURDAY_START, SATURDAY_END),
    )
    monkeypatch.setattr(
        "cm_agents.agents.deployment.move_state",
        lambda *_args, **_kwargs: {"state": "-1"},
    )
    monkeypatch.setattr(
        "cm_agents.agents.deployment.update_fields",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "cm_agents.agents.deployment.ensure_change_task",
        lambda *_args, **_kwargs: {"sys_id": "task", "state": "1"},
    )
    pin(SATURDAY_INSIDE)
    token = activate(
        AgentContext(
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            {},
            {"cis": [{"name": "syn-ful-api", "environment": "prod"}]},
        )
    )
    try:
        result = run_deployment(
            {
                "thread_id": "SYN-retry",
                "change_sys_id": "change",
                "change_number": "CHG1",
                "change_type": "normal",
                "service_tier": 2,
                "release_member": False,
                "authorization": {"go_no_go": {"decision": "go"}},
                "affected_cis": [{"name": "syn-ful-api", "sys_id": "ci"}],
                "request": {"deployment_strategy": "canary"},
            }
        )
    finally:
        reset(token)
        pin(None)
    assert calls["deploy"] == 1
    assert calls["rollback"] == 0
    assert result["deployment"]["outcome"] == "blocked"
    assert "recorded failure" in result["error"]


def _state(change_type: str, *, decision: str = "", tier: int = 3) -> dict[str, Any]:
    authorization: dict[str, Any] = {}
    if decision:
        authorization = {"go_no_go": {"decision": decision}}
    return {
        "change_type": change_type,
        "service_tier": tier,
        "release_member": False,
        "authorization": authorization,
    }


def _record(state: str, start: str, end: str) -> dict[str, str]:
    return {"state": state, "start_date": start, "end_date": end, "number": "CHG1"}
