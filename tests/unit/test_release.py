"""Release readiness and risk. No network and no model calls."""

import inspect
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
    unexpected_change_tasks,
)
from cm_agents.enablement.route import route_after_authorization
from cm_agents.graphs.release_graph import _after_go, _after_readiness, build_release_graph

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


def test_a_release_failing_several_checks_reports_them_all_together() -> None:
    members = [
        _member("CHG1001", "-2", ci="syn-pay-api"),
        _member("CHG1002", "-3", risk="", ci="syn-store-cart"),
        _member("CHG1003", "-4"),
    ]
    for member in members:
        del member["checklist"]
    failures = readiness_failures(
        members,
        release_service="SYN Online Store",
        ci_service={
            "syn-store-web": "SYN Online Store",
            "syn-store-cart": "SYN Online Store",
            "syn-pay-api": "SYN Payments",
        },
        blocking_conflicts=["ci_already_scheduled"],
        freeze="SYN Holiday Peak Freeze",
        open_p1_p2=["INC1 priority 1"],
        notes_ready=False,
        check_notes=True,
        plan_quality=False,
    )
    assert failures == [
        "CHG1002 failed the authorization check: awaiting authorization",
        "CHG1003 failed the authorization check: awaiting authorization",
        "CHG1001 failed the service check: syn-pay-api is not in SYN Online Store",
        "CHG1002 failed the member risk check: risk is missing",
        "release failed the freeze check: SYN Holiday Peak Freeze",
        "release failed the conflict check: ci_already_scheduled",
        "release failed the open incident check: INC1 priority 1",
        "release failed the release notes check: notes were not generated",
    ]
    assert not any("plan quality" in failure for failure in failures)
    detail = "; ".join(failures)
    assert _after_readiness({"readiness": {"passed": False, "detail": detail}}) == "wait"


def test_plan_quality_is_checked_once_every_member_is_authorized() -> None:
    member = _member("CHG1001", "-2")
    member["checklist"]["backout_trigger"] = False
    failures = readiness_failures(
        [member],
        release_service="SYN Online Store",
        ci_service={"syn-store-web": "SYN Online Store"},
        blocking_conflicts=[],
        freeze=None,
        open_p1_p2=[],
        notes_ready=True,
        check_notes=True,
    )
    assert failures == ["CHG1001 failed the plan quality check: backout_trigger"]


def test_the_interrupt_names_every_failure_and_says_plan_quality_is_held(monkeypatch) -> None:
    members = [
        {**_member("CHG1001", "-2", ci="syn-pay-api"), "sys_id": "m1"},
        {**_member("CHG1002", "-3"), "sys_id": "m2"},
    ]
    record = {
        "sys_id": "rel",
        "number": "CHG2000",
        "short_description": release_module.release_summary("SYN Online Store", "2026.11.0"),
        "start_date": "2026-11-21 03:00:00",
        "end_date": "2026-11-21 05:00:00",
    }
    fixtures = {
        "cis": [
            {"name": "syn-store-web", "service": "SYN Online Store"},
            {"name": "syn-pay-api", "service": "SYN Payments"},
        ]
    }
    context = SimpleNamespace(client=None, fixtures=fixtures, policy={"freezes": []})
    monkeypatch.setattr(release_module, "current", lambda: context)
    monkeypatch.setattr(release_module, "_load_release", lambda client, thread: record)
    monkeypatch.setattr(release_module, "_member_views", lambda client, rel, state: members)
    monkeypatch.setattr(release_module, "_service_tier", lambda fixtures, service: 1)
    monkeypatch.setattr(
        release_module, "_conflicts", lambda client, rows, rel: (["blackout"], ["blackout"])
    )
    monkeypatch.setattr(
        release_module, "_open_incidents", lambda client, fixtures, service: ["INC1 priority 1"]
    )
    monkeypatch.setattr(release_module, "notes_ready", lambda version: False)

    def no_model(*args, **kwargs):
        raise AssertionError("the model was called while a member awaits authorization")

    monkeypatch.setattr(release_module, "_judge_members", no_model)
    monkeypatch.setattr(release_module, "_write_notes", no_model)
    result = release_module.run_readiness({"thread_id": "SYN-S06-test"})
    detail = result["readiness"]["detail"]
    assert result["readiness"]["passed"] is False
    assert "member_checks" not in result
    for expected in (
        "CHG1002 failed the authorization check: awaiting authorization",
        "CHG1001 failed the service check: syn-pay-api is not in SYN Online Store",
        "release failed the conflict check: blackout",
        "release failed the open incident check: INC1 priority 1",
        "release failed the release notes check: notes were not generated",
        release_module.PLAN_QUALITY_HELD,
    ):
        assert expected in detail


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
