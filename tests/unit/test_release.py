"""Release readiness and risk. No network and no model calls."""

import inspect
from datetime import datetime
from types import SimpleNamespace

from langgraph.checkpoint.sqlite import SqliteSaver

from cm_agents.agents import release as release_module
from cm_agents.agents.release import (
    authorization_failures,
    blocking_conflict_types,
    highest_member_tier,
    implementation_task_name,
    member_close_note,
    readiness_failures,
    resolve_service,
    run_release_close,
    run_release_deploy,
    unexpected_change_tasks,
)
from cm_agents.clock import pin
from cm_agents.data.import_time import UTC
from cm_agents.enablement.route import route_after_authorization
from cm_agents.graphs.release_graph import _after_go, _after_readiness, build_release_graph
from cm_agents.servicenow.changes import STATE_REVIEW, ChangeError

ENVIRONMENTS = ("DEV", "TEST", "STAGE", "PROD")


def _member(number: str, state: str, risk: str = "4", ci: str = "syn-store-web") -> dict:
    return {
        "number": number,
        "state": state,
        "risk": risk,
        "ci_names": [ci],
        "checklist": {
            "ordered_backout": True,
            "backout_trigger": True,
            "test_criteria": True,
            "implementation_owner": True,
        },
    }


def test_a_release_reports_every_deterministic_failure_together() -> None:
    members = [
        _member("CHG1001", "-2"),
        _member("CHG1002", "-3", ci="syn-pay-api"),
    ]
    members[0]["checklist"]["ordered_backout"] = False
    failures = readiness_failures(
        members,
        release_service="SYN Online Store",
        ci_service={"syn-store-web": "SYN Online Store", "syn-pay-api": "SYN Payments"},
        blocking_conflicts=["ci_already_scheduled"],
        freeze="SYN Holiday Peak Freeze",
        open_p1_p2=["INC1 priority 1"],
        notes_ready=False,
        check_notes=True,
    )
    assert failures == [
        "CHG1002 failed the authorization check: awaiting authorization",
        "plan quality was not checked because a member is awaiting authorization",
        "CHG1002 failed the service check: syn-pay-api is not in SYN Online Store",
        "release failed the freeze check: SYN Holiday Peak Freeze",
        "release failed the conflict check: ci_already_scheduled",
        "release failed the open incident check: INC1 priority 1",
        "release failed the release notes check: notes were not generated",
    ]
    assert not any("ordered_backout" in item for item in failures)
    assert _after_readiness({"readiness": {"passed": False, "detail": failures[0]}}) == "wait"


def test_readiness_passes_only_when_notes_exist_and_the_other_checks_are_clear() -> None:
    members = [_member("CHG1001", "-2"), _member("CHG1002", "-2", ci="syn-shared-sql")]
    common = {
        "release_service": "SYN Online Store",
        "ci_service": {"syn-store-web": "SYN Online Store", "syn-other": "SYN Payments"},
        "blocking_conflicts": [],
        "freeze": None,
        "open_p1_p2": [],
    }
    waiting = readiness_failures(members, notes_ready=False, check_notes=True, **common)
    assert waiting == ["release failed the release notes check: notes were not generated"]
    assert readiness_failures(members, notes_ready=True, check_notes=True, **common) == []
    assert _after_readiness({"readiness": {"passed": True}}) == "risk"


def test_a_foreign_ci_and_a_blocking_conflict_fail_after_authorization() -> None:
    members = [_member("CHG1001", "-2", ci="syn-pay-api")]
    failures = readiness_failures(
        [members[0]],
        release_service="SYN Online Store",
        ci_service={"syn-pay-api": "SYN Payments"},
        blocking_conflicts=[],
        freeze=None,
        open_p1_p2=[],
        notes_ready=True,
        check_notes=False,
    )
    assert "syn-pay-api" in failures[0]
    kept = blocking_conflict_types(
        [
            {"type": "not_in_maintenance_window", "conflicting_change": "outside"},
            {"type": "ci_already_scheduled", "conflicting_change": "member-1"},
            {"type": "blackout", "conflicting_change": "outside"},
        ],
        own_ids={"member-1"},
    )
    assert kept == ["blackout"]


def test_release_risk_is_the_highest_member_tier_with_no_rubric() -> None:
    assert highest_member_tier(["4", "3", "2"]) == "high"
    assert highest_member_tier(["4", "4"]) == "low"
    assert highest_member_tier(["3"]) == "moderate"
    source = inspect.getsource(release_module)
    assert "score_change" not in source
    assert "run_risk" not in source
    missing = readiness_failures(
        [_member("CHG1001", "-2", risk="")],
        release_service="SYN Online Store",
        ci_service={"syn-store-web": "SYN Online Store"},
        blocking_conflicts=[],
        freeze=None,
        open_p1_p2=[],
        notes_ready=True,
        check_notes=False,
    )
    assert missing == ["CHG1001 failed the member risk check: risk is missing"]


def test_missing_member_risk_is_reported_while_authorization_is_pending() -> None:
    failures = readiness_failures(
        [_member("CHG1001", "-3", risk="")],
        release_service="SYN Online Store",
        ci_service={"syn-store-web": "SYN Online Store"},
        blocking_conflicts=[],
        freeze=None,
        open_p1_p2=[],
        notes_ready=True,
        check_notes=False,
    )
    assert failures == [
        "CHG1001 failed the authorization check: awaiting authorization",
        "plan quality was not checked because a member is awaiting authorization",
        "CHG1001 failed the member risk check: risk is missing",
    ]
    assert not any("plan quality check:" in item for item in failures)


def test_model_tasks_are_not_treated_as_member_tasks() -> None:
    assert (
        unexpected_change_tasks(
            [
                {"short_description": "Implement"},
                {"short_description": "Post implementation testing"},
            ]
        )
        == []
    )
    assert unexpected_change_tasks([{"short_description": "SYN PROD implementation"}]) == [
        "SYN PROD implementation"
    ]


def test_stage_tasks_and_member_close_notes() -> None:
    assert [implementation_task_name(env) for env in ENVIRONMENTS] == [
        "SYN DEV implementation",
        "SYN TEST implementation",
        "SYN STAGE implementation",
        "SYN PROD implementation",
    ]
    note = member_close_note("CHG2000", "SYN RELEASE SYN Online Store 2026.11.0")
    assert "CHG2000" in note
    assert "SYN RELEASE SYN Online Store 2026.11.0" in note


def test_members_still_hand_off_and_a_release_waits_for_go() -> None:
    assert (
        route_after_authorization(
            change_type="normal",
            pending_step=None,
            rejected=False,
            release_member=True,
        )
        == "release_handoff"
    )
    assert (
        route_after_authorization(
            change_type="normal",
            pending_step=None,
            rejected=False,
            release_member=False,
        )
        == "go_no_go"
    )
    assert _after_go({"authorization": {"go_no_go": {"decision": "go"}}}) == "deploy"
    assert _after_go({"authorization": {"go_no_go": {"decision": "no-go"}}}) == "end"
    assert authorization_failures([]) == [
        "release failed the authorization check: no member changes"
    ]


def test_release_graph_compiles() -> None:
    with SqliteSaver.from_conn_string(":memory:") as saver:
        graph = build_release_graph(saver)
        assert "readiness" in graph.nodes
        assert "auth_wait" in graph.nodes
        assert "go_no_go" in graph.nodes
        assert "deploy" in graph.nodes
        assert "review" in graph.nodes


def test_service_alias() -> None:
    assert resolve_service("STORE") == "SYN Online Store"
    assert resolve_service("FUL") == "SYN Order Fulfillment"
    assert resolve_service("SYN Payments") == "SYN Payments"


def test_the_review_move_happens_after_the_actual_end_is_stamped(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def stamp(_client: object, _change_id: str, field: str) -> None:
        calls.append(("stamp", field))

    def move(_client: object, _kind: str, _change_id: str, target: str) -> dict[str, str]:
        calls.append(("move", target))
        return {"state": target}

    monkeypatch.setattr(release_module, "_stamp", stamp)
    monkeypatch.setattr(release_module, "move_state", move)
    monkeypatch.setattr(
        release_module,
        "read_change",
        lambda *_args, **_kwargs: {"state": "-1", "number": "CHG1"},
    )
    monkeypatch.setattr(release_module, "_member_views", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(release_module, "_deploy_environment", lambda *_args, **_kwargs: "passed")
    monkeypatch.setattr(release_module, "current", lambda: SimpleNamespace(client=object()))
    result = run_release_deploy(
        {
            "change_sys_id": "rel",
            "thread_id": "SYN-S06-unit",
            "change_number": "CHG1",
            "authorization": {"go_no_go": {"decision": "go"}},
        }
    )
    assert result["deployment"]["outcome"] == "verified"
    assert calls.index(("stamp", "work_end")) < calls.index(("move", STATE_REVIEW))


class _ActualDates:
    """Reject a table update whose actual end is before its actual start."""

    def __init__(self) -> None:
        self.row = {
            "sys_id": "rel",
            "number": "CHG1",
            "state": "0",
            "short_description": "SYN RELEASE SYN Online Store 2026.11.0",
            "work_start": "2026-11-15 03:30:00",
            "work_end": "2026-11-13 19:08:10",
            "close_code": "",
            "close_notes": "",
        }

    def get_record(self, _table: str, _sys_id: str, **_kwargs: object) -> dict[str, str]:
        return dict(self.row)

    def update_record(self, _table: str, _sys_id: str, fields: dict[str, str]) -> dict[str, str]:
        proposed = dict(self.row)
        proposed.update(fields)
        start = str(proposed.get("work_start") or "")
        end = str(proposed.get("work_end") or "")
        if start and end and start > end:
            raise ChangeError("Actual Start/End Date Validation")
        self.row.update(fields)
        return dict(self.row)


def test_close_repairs_an_inverted_actual_end_before_close_notes(monkeypatch) -> None:
    client = _ActualDates()
    pin(datetime(2026, 11, 15, 3, 30, tzinfo=UTC))
    monkeypatch.setattr(release_module, "_member_views", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(release_module, "_release_close_notes", lambda *_args, **_kwargs: "notes")
    monkeypatch.setattr(
        release_module,
        "move_state",
        lambda *_args, **_kwargs: {**client.row, "state": "3"},
    )
    monkeypatch.setattr(
        release_module,
        "write_note",
        lambda note_client, sys_id, **_kwargs: note_client.update_record(
            "change_request", sys_id, {"work_notes": "closed"}
        ),
    )
    monkeypatch.setattr(release_module, "current", lambda: SimpleNamespace(client=client))
    try:
        result = run_release_close(
            {
                "change_sys_id": "rel",
                "thread_id": "SYN-S06-unit",
                "change_number": "CHG1",
                "deployment": {"outcome": "verified", "stages": []},
            }
        )
    finally:
        pin(None)
    assert result["review"]["done"] is True
    assert client.row["work_end"] == "2026-11-15 03:30:00"
    assert client.row["close_code"] == "successful"
