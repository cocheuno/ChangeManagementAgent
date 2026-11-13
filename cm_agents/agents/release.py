"""Release readiness, staged deployment, and member closure.

A release is a normal change named ``SYN RELEASE <service> <version>``.
Member changes point at it through ``parent``. docs/DISCOVERY.md item 10.

The readiness gate runs before the release is submitted for authorization.
Risk is the highest member tier, copied in code. There is no separate
assessment. Authorization is the go-live authorization. Go/no-go comes after
that. The release carries one implementation task per environment. The normal
change model also inserts ``Implement`` and ``Post implementation testing``
when a change enters Implement. Those rows are left in place. The agent
cannot delete ``change_task``, and the model is not edited. Member changes
get no agent tasks. They close with the release, and the close notes name it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from cm_agents.agents.context import current
from cm_agents.agents.risk import judge_plans
from cm_agents.audit import record_audit
from cm_agents.clock import now
from cm_agents.data.import_time import UTC, parse_utc
from cm_agents.deploy.simulator import default_path, passes_thresholds, run_deploy, run_rollback
from cm_agents.enablement.guard import blocks_schedule
from cm_agents.enablement.risk_score import CHECKLIST, RISK_VALUE, impact_for_tier
from cm_agents.enablement.windows import freeze_hit
from cm_agents.llm import complete, record_block
from cm_agents.servicenow.changes import (
    STATE_CLOSED,
    STATE_IMPLEMENT,
    STATE_REVIEW,
    STATE_SCHEDULED,
    ChangeError,
    close_change_task,
    conflicts_for,
    create_change,
    ensure_change_task,
    find_by_correlation,
    group_id,
    move_state,
    read_change,
    remember_change,
    service_ci,
    update_fields,
    write_dates,
    write_note,
    write_risk,
)
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import repo_root

ENVIRONMENTS = ("DEV", "TEST", "STAGE", "PROD")
NOTE_SECTIONS = (
    "## User-facing changes",
    "## Support and service desk notes",
    "## Known errors and workarounds",
)
# The normal model inserts these on the way into Implement and cancels them
# on the way out. change_task delete is HTTP 403 for the agent user.
MODEL_TASK_NAMES = frozenset({"Implement", "Post implementation testing"})
SERVICE_ALIASES = {
    "STORE": "SYN Online Store",
    "PAYMENTS": "SYN Payments",
    "FULFILLMENT": "SYN Order Fulfillment",
    "FUL": "SYN Order Fulfillment",
    "HR": "SYN HR Portal",
}
_TIER_BY_VALUE = {"2": "high", "3": "moderate", "4": "low"}
_TIER_RANK = {"high": 3, "moderate": 2, "low": 1}
_MEMBER_FIELDS = [
    "sys_id",
    "number",
    "state",
    "risk",
    "cmdb_ci",
    "short_description",
    "description",
    "justification",
    "implementation_plan",
    "backout_plan",
    "test_plan",
    "close_code",
    "close_notes",
]


class ReleaseNotes(BaseModel):
    user_facing_changes: str = Field(min_length=1)
    support_and_service_desk_notes: str = Field(min_length=1)
    known_errors_and_workarounds: str = Field(min_length=1)


class CloseNotes(BaseModel):
    close_notes: str = Field(min_length=1)


NOTES_FAILURE = "release failed the release notes check: notes were not generated"
PLAN_QUALITY_HELD = "plan quality check held until every member is authorized"


def resolve_service(token: str) -> str:
    text = token.strip()
    if text in SERVICE_ALIASES:
        return SERVICE_ALIASES[text]
    folded = text.casefold()
    for alias, name in SERVICE_ALIASES.items():
        if folded == alias.casefold() or folded == name.casefold():
            return name
    if text.startswith("SYN "):
        return text
    raise ValueError(f"unknown service {token}")


def release_summary(service: str, version: str) -> str:
    return f"SYN RELEASE {service} {version}"


def parse_release_summary(summary: str) -> tuple[str, str]:
    prefix = "SYN RELEASE "
    if not summary.startswith(prefix):
        raise ChangeError(f"release summary does not match the naming rule: {summary}")
    service, version = summary[len(prefix) :].rsplit(" ", 1)
    if not service or not version:
        raise ChangeError(f"release summary does not match the naming rule: {summary}")
    return service, version


def implementation_task_name(environment: str) -> str:
    return f"SYN {environment} implementation"


def member_close_note(number: str, summary: str) -> str:
    return f"Closed with release {number} {summary}."


def highest_member_tier(values: list[str]) -> str:
    """Most severe stored risk choice. High, then Moderate, then Low."""
    if not values:
        raise ValueError("no member risk")
    best = ""
    best_rank = -1
    for value in values:
        name = _TIER_BY_VALUE.get(str(value))
        if name is None:
            raise ValueError(f"unknown risk {value}")
        rank = _TIER_RANK[name]
        if rank > best_rank:
            best = name
            best_rank = rank
    return best


def authorization_failures(members: list[dict[str, Any]]) -> list[str]:
    """Members that are not Scheduled. This check does not call a model."""
    if not members:
        return ["release failed the authorization check: no member changes"]
    failures = []
    for member in members:
        if str(member.get("state") or "") != STATE_SCHEDULED:
            number = str(member.get("number") or "member")
            failures.append(f"{number} failed the authorization check: awaiting authorization")
    return failures


def blocking_conflict_types(rows: list[dict[str, Any]], *, own_ids: set[str]) -> list[str]:
    """CI overlap and blackout. A sibling member is not an outside conflict.

    ``not_in_maintenance_window`` is not a block. Policy code owns that check.
    """
    found: list[str] = []
    for row in rows:
        other = str(row.get("conflicting_change") or "")
        if other and other in own_ids:
            continue
        kind = str(row.get("type") or "")
        if blocks_schedule(kind, "normal"):
            found.append(kind)
    return found


def readiness_failures(
    members: list[dict[str, Any]],
    *,
    release_service: str,
    ci_service: dict[str, str],
    blocking_conflicts: list[str],
    freeze: str | None,
    open_p1_p2: list[str],
    notes_ready: bool,
    check_notes: bool,
    plan_quality: bool = True,
) -> list[str]:
    """Every deterministic readiness failure, reported together.

    ``plan_quality`` is false while a member awaits authorization, because the
    checklist comes from a model call that is held until then. The caller
    generates notes only after the other checks pass.
    """
    failures = authorization_failures(members)
    for member in members:
        number = str(member.get("number") or "member")
        if str(member.get("risk") or "") not in _TIER_BY_VALUE:
            failures.append(f"{number} failed the member risk check: risk is missing")
        checklist = member.get("checklist") or {}
        for name in CHECKLIST if plan_quality else ():
            if not checklist.get(name):
                failures.append(f"{number} failed the plan quality check: {name}")
        names = [str(ci) for ci in (member.get("ci_names") or []) if str(ci)]
        if not names:
            failures.append(f"{number} failed the service check: no affected CI")
        for ci_name in names:
            if ci_name.startswith("syn-shared-"):
                continue
            if ci_service.get(ci_name) != release_service:
                failures.append(
                    f"{number} failed the service check: {ci_name} is not in {release_service}"
                )
    if freeze:
        failures.append(f"release failed the freeze check: {freeze}")
    for conflict in blocking_conflicts:
        failures.append(f"release failed the conflict check: {conflict}")
    for incident in open_p1_p2:
        failures.append(f"release failed the open incident check: {incident}")
    if check_notes and not notes_ready:
        failures.append(NOTES_FAILURE)
    return failures


def unexpected_change_tasks(tasks: list[dict[str, Any]]) -> list[str]:
    """Names that are not the two tasks the normal change model inserts."""
    names: list[str] = []
    for task in tasks:
        name = str(task.get("short_description") or "")
        if name in MODEL_TASK_NAMES:
            continue
        names.append(name or "(unnamed)")
    return names


def notes_path(version: str):
    return repo_root() / "reports" / "release" / f"{version}.md"


def notes_ready(version: str) -> bool:
    path = notes_path(version)
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    return all(section in text for section in NOTE_SECTIONS)


def run_readiness(state: dict[str, Any]) -> dict[str, Any]:
    """Gate the release. Do not move it to Assess while a check is failing."""
    if state.get("error"):
        return {}
    if (state.get("readiness") or {}).get("passed"):
        return {}
    ctx = current()
    record = _load_release(ctx.client, state["thread_id"])
    service, version = parse_release_summary(str(record.get("short_description") or ""))
    members = _member_views(ctx.client, str(record["sys_id"]), state)
    base = {
        "change_sys_id": str(record["sys_id"]),
        "change_number": str(record.get("number") or ""),
        "change_type": "normal",
        "release_member": False,
        "service": service,
        "version": version,
        "service_tier": _service_tier(ctx.fixtures, service),
    }
    # The plan-quality check calls a model. It is held until every member is authorized.
    pending = authorization_failures(members)
    judged = {} if pending else _judge_members(state, members)
    for member in members:
        if not pending:
            member["checklist"] = judged[str(member["sys_id"])]
    start_text = str(record.get("start_date") or "")
    end_text = str(record.get("end_date") or "")
    if not start_text or not end_text:
        raise ChangeError("release window is missing")
    blocking, observed = _conflicts(ctx.client, members, str(record["sys_id"]))
    freeze = freeze_hit(
        service,
        parse_utc(start_text),
        parse_utc(end_text),
        list(ctx.policy.get("freezes") or []),
    )
    incidents = _open_incidents(ctx.client, ctx.fixtures, service)
    ci_service = {
        str(row["name"]): str(row.get("service") or "") for row in ctx.fixtures.get("cis") or []
    }
    failures = readiness_failures(
        members,
        release_service=service,
        ci_service=ci_service,
        blocking_conflicts=blocking,
        freeze=freeze,
        open_p1_p2=incidents,
        notes_ready=notes_ready(version),
        check_notes=True,
        plan_quality=not pending,
    )
    checks = {"member_checks": judged} if judged else {}
    # Notes are written below, once every other check has passed.
    if any(failure != NOTES_FAILURE for failure in failures):
        detail = "; ".join(failures)
        if pending:
            detail += f"; {PLAN_QUALITY_HELD}"
        return {
            **base,
            **checks,
            "readiness": {"passed": False, "detail": detail},
        }
    _write_notes(state, version, service, members)
    if not notes_ready(version):
        raise ChangeError("release notes file is missing a required section")
    tier = highest_member_tier([str(member.get("risk") or "") for member in members])
    plans = _plans(record)
    return {
        **base,
        **checks,
        "readiness": {"passed": True, "detail": ""},
        "impacted_service_names": [service],
        "request": plans,
        "schedule": {
            "start": start_text,
            "end": end_text,
            "requested_start": start_text,
            "requested_end": end_text,
            "maintenance": "policy",
            "conflict_types": observed,
        },
        "risk": {
            "tier": tier,
            "score": 0,
            "risk": RISK_VALUE[tier],
            "impact": impact_for_tier(int(base["service_tier"])),
            "factors": [
                {
                    "name": "member_tier",
                    "points": 0,
                    "evidence": f"highest member tier is {tier}",
                }
            ],
            "written": False,
        },
    }


def apply_release_risk(state: dict[str, Any]) -> dict[str, Any]:
    """Copy the highest member tier onto the release. No rubric and no calculator."""
    if state.get("error"):
        return {}
    risk = dict(state.get("risk") or {})
    if risk.get("written"):
        return {}
    if risk.get("tier") not in _TIER_RANK or not risk.get("risk") or not risk.get("impact"):
        return {"error": "release risk was not taken from the member tiers"}
    written = write_risk(
        current().client,
        state["change_sys_id"],
        str(risk["risk"]),
        str(risk["impact"]),
    )
    if str(written.get("risk") or "") != str(risk["risk"]):
        raise ChangeError("release risk did not keep the member tier")
    risk["written"] = True
    write_note(
        current().client,
        state["change_sys_id"],
        thread_id=state["thread_id"],
        agent="release",
        decision="risk",
        reason=f"highest member tier is {risk['tier']}",
        record=str(state.get("change_number") or ""),
    )
    return {"risk": risk}


def run_release_deploy(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("error"):
        return {}
    done = state.get("deployment") or {}
    if done.get("outcome") in {"verified", "failed"}:
        return {}
    ctx = current()
    record = read_change(ctx.client, state["change_sys_id"])
    blocked = _deploy_precondition(state, record)
    if blocked:
        return {"error": blocked, "deployment": {"outcome": "blocked"}}
    if str(record.get("state") or "") == STATE_SCHEDULED:
        record = move_state(ctx.client, "normal", state["change_sys_id"], STATE_IMPLEMENT)
    _stamp(ctx.client, state["change_sys_id"], "work_start")
    members = _member_views(ctx.client, state["change_sys_id"], state)
    stages: list[dict[str, str]] = []
    for environment in ENVIRONMENTS:
        outcome = _deploy_environment(state, members, environment)
        stages.append({"environment": environment, "result": outcome})
        if outcome != "passed":
            return {
                "error": f"{environment} did not pass",
                "deployment": {
                    "outcome": "failed",
                    "stages": stages,
                    "change_state": STATE_IMPLEMENT,
                },
            }
    record = move_state(ctx.client, "normal", state["change_sys_id"], STATE_REVIEW)
    return {
        "deployment": {
            "outcome": "verified",
            "stages": stages,
            "change_state": str(record.get("state") or ""),
        }
    }


def run_release_close(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("error"):
        return {}
    if (state.get("review") or {}).get("done"):
        return {}
    if str((state.get("deployment") or {}).get("outcome") or "") != "verified":
        return {"error": "release review requires every stage to pass"}
    ctx = current()
    record = read_change(ctx.client, state["change_sys_id"])
    if str(record.get("state") or "") != STATE_REVIEW:
        return {
            "error": f"release review expected state {STATE_REVIEW} and found {record.get('state')}"
        }
    members = _member_views(ctx.client, state["change_sys_id"], state)
    number = str(record.get("number") or state.get("change_number") or "")
    summary = str(record.get("short_description") or "")
    for member in members:
        _close_member(ctx.client, member, number, summary)
    notes = _release_close_notes(state, number)
    update_fields(
        ctx.client,
        state["change_sys_id"],
        {"close_code": "successful", "close_notes": notes},
    )
    _stamp(ctx.client, state["change_sys_id"], "work_end")
    closed = move_state(ctx.client, "normal", state["change_sys_id"], STATE_CLOSED)
    if str(closed.get("state") or "") != STATE_CLOSED:
        raise ChangeError(f"release state is {closed.get('state')} after a move to Closed")
    if str(closed.get("close_code") or "") != "successful":
        raise ChangeError(f"release close_code is {closed.get('close_code')}")
    write_note(
        ctx.client,
        state["change_sys_id"],
        thread_id=state["thread_id"],
        agent="release",
        decision="closed",
        reason="close code successful",
        record=number,
    )
    return {
        "review": {
            "done": True,
            "route": "closed",
            "close_code": "successful",
            "change_state": STATE_CLOSED,
        }
    }


def create_release_change(
    client: ServiceNowClient,
    *,
    service: str,
    version: str,
    start: str,
    end: str,
    thread_id: str,
) -> dict[str, Any]:
    """Create the release change in New. Do not submit it for authorization."""
    existing = find_by_correlation(client, thread_id)
    if existing:
        return existing
    summary = release_summary(service, version)
    record = create_change(
        client,
        "normal",
        {
            "short_description": summary,
            "description": f"Release {version} for {service}.",
            "correlation_id": thread_id,
        },
    )
    remember_change(str(record["sys_id"]), thread_id)
    service_id = service_ci(client, service)
    if not service_id:
        raise ChangeError(f"service CI {service} was not found")
    update_fields(
        client,
        str(record["sys_id"]),
        {
            "assignment_group": group_id(client, "Change Management"),
            "cmdb_ci": service_id,
            "justification": "Make the authorized member changes available together.",
            "implementation_plan": (
                "1. Deploy each member CI through DEV, TEST, STAGE, and PROD. "
                "Owner is Change Management."
            ),
            "backout_plan": (
                "1. Trigger the backout when a stage fails. "
                "2. Restore the previous version of each member CI. "
                "The backout finishes within 30 minutes."
            ),
            "test_plan": (
                "1. Record the result of each stage. "
                "Success criteria: DEV, TEST, STAGE, and PROD all pass."
            ),
        },
    )
    write_dates(client, str(record["sys_id"]), start, end)
    stored = read_change(client, str(record["sys_id"]))
    if str(stored.get("state") or "") != "-5":
        raise ChangeError("release new moved the change out of New")
    return stored


def _load_release(client: ServiceNowClient, thread_id: str) -> dict[str, Any]:
    found = find_by_correlation(client, thread_id)
    if not found:
        raise ChangeError("release change was not found")
    return found


def _member_views(
    client: ServiceNowClient, release_id: str, state: dict[str, Any]
) -> list[dict[str, Any]]:
    rows = client.get_table(
        "change_request",
        query=f"parent={release_id}",
        fields=_MEMBER_FIELDS,
        limit=20,
    )
    views = []
    stored = state.get("member_checks") or {}
    for row in rows:
        sys_id = str(row["sys_id"])
        view = dict(row)
        view["ci_names"] = _ci_names(client, sys_id, str(row.get("cmdb_ci") or ""))
        checklist = stored.get(sys_id)
        if isinstance(checklist, dict):
            view["checklist"] = checklist
        views.append(view)
    return views


def _judge_members(
    state: dict[str, Any], members: list[dict[str, Any]]
) -> dict[str, dict[str, bool]]:
    judged: dict[str, dict[str, bool]] = {}
    stored = state.get("member_checks") or {}
    for member in members:
        sys_id = str(member["sys_id"])
        previous = stored.get(sys_id)
        if isinstance(previous, dict) and all(name in previous for name in CHECKLIST):
            judged[sys_id] = {name: bool(previous[name]) for name in CHECKLIST}
            continue
        judged[sys_id] = judge_plans(
            {
                "thread_id": state["thread_id"],
                "change_number": str(member.get("number") or ""),
                "request": {
                    "implementation_plan": member.get("implementation_plan"),
                    "backout_plan": member.get("backout_plan"),
                    "test_plan": member.get("test_plan"),
                },
            }
        )
    return judged


def _conflicts(
    client: ServiceNowClient, members: list[dict[str, Any]], release_id: str
) -> tuple[list[str], list[str]]:
    own_ids = {str(member["sys_id"]) for member in members}
    own_ids.add(release_id)
    blocking: list[str] = []
    observed: list[str] = []
    for member in members:
        rows, status = conflicts_for(client, str(member["sys_id"]))
        if status != "ok":
            blocking.append(f"unreadable for {member.get('number')}")
            continue
        for row in rows:
            kind = str(row.get("type") or "")
            if kind and kind not in observed:
                observed.append(kind)
        blocking.extend(blocking_conflict_types(rows, own_ids=own_ids))
    return blocking, observed


def _open_incidents(client: ServiceNowClient, fixtures: dict[str, Any], service: str) -> list[str]:
    owned = {
        str(row["name"])
        for row in fixtures.get("cis") or []
        if str(row.get("service") or "") == service
    }
    rows = client.get_table(
        "incident",
        query="active=true^priorityIN1,2",
        fields=["number", "priority", "cmdb_ci"],
        limit=100,
    )
    found = []
    for row in rows:
        ci_id = str(row.get("cmdb_ci") or "")
        if not ci_id:
            continue
        record = client.get_record("cmdb_ci", ci_id, fields=["name"])
        name = str(record.get("name") or "")
        if name in owned:
            found.append(f"{row.get('number')} priority {row.get('priority')} on {name}")
    return found


def _ci_names(client: ServiceNowClient, change_id: str, primary_id: str) -> list[str]:
    names: list[str] = []
    if primary_id:
        primary = client.get_record("cmdb_ci", primary_id, fields=["name"])
        primary_name = str(primary.get("name") or "")
        if primary_name:
            names.append(primary_name)
    links = client.get_table(
        "task_ci",
        query=f"task={change_id}",
        fields=["ci_item"],
        limit=20,
    )
    for link in links:
        ci_id = str(link.get("ci_item") or "")
        if not ci_id or ci_id == primary_id:
            continue
        record = client.get_record("cmdb_ci", ci_id, fields=["name"])
        name = str(record.get("name") or "")
        if name and name not in names:
            names.append(name)
    return names


def _plans(record: dict[str, Any]) -> dict[str, str]:
    extra = current().client.get_record(
        "change_request",
        str(record["sys_id"]),
        fields=["justification", "implementation_plan", "backout_plan", "test_plan", "description"],
    )
    return {
        "summary": str(record.get("short_description") or ""),
        "description": str(extra.get("description") or ""),
        "justification": str(extra.get("justification") or ""),
        "implementation_plan": str(extra.get("implementation_plan") or ""),
        "backout_plan": str(extra.get("backout_plan") or ""),
        "test_plan": str(extra.get("test_plan") or ""),
    }


def _service_tier(fixtures: dict[str, Any], service: str) -> int:
    for row in fixtures.get("services") or []:
        if str(row.get("name") or "") == service:
            return int(row["tier"])
    raise ChangeError(f"service tier was not found for {service}")


def _write_notes(
    state: dict[str, Any], version: str, service: str, members: list[dict[str, Any]]
) -> None:
    if notes_ready(version):
        return
    lines = [f"Release {version} for {service}."]
    for member in members:
        lines.append(
            "\n".join(
                [
                    f"Member {member.get('number')}: {member.get('short_description')}",
                    f"Description: {member.get('description')}",
                    f"Implementation: {member.get('implementation_plan')}",
                    f"Backout: {member.get('backout_plan')}",
                    f"Test: {member.get('test_plan')}",
                ]
            )
        )
    draft = complete(
        current().settings,
        ReleaseNotes,
        system=(
            "Write release notes from the member records only. "
            "Fill all three sections. Do not invent changes that are not in the records."
        ),
        user=record_block("\n\n".join(lines)),
        thread_id=state["thread_id"],
        agent="release",
        action="release_notes",
        record=str(state.get("change_number") or version),
    )
    path = notes_path(version)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# Release notes {version}",
                "",
                "## User-facing changes",
                draft.user_facing_changes.strip(),
                "",
                "## Support and service desk notes",
                draft.support_and_service_desk_notes.strip(),
                "",
                "## Known errors and workarounds",
                draft.known_errors_and_workarounds.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )


def _deploy_precondition(state: dict[str, Any], record: dict[str, Any]) -> str:
    decision = ((state.get("authorization") or {}).get("go_no_go") or {}).get("decision")
    if decision != "go":
        return "release has no go decision"
    current_state = str(record.get("state") or "")
    if current_state not in {STATE_SCHEDULED, STATE_IMPLEMENT}:
        return "release is not Scheduled"
    if current_state != STATE_SCHEDULED:
        return ""
    start_text = str(record.get("start_date") or "")
    end_text = str(record.get("end_date") or "")
    if not start_text or not end_text:
        return "approved window is missing"
    start = parse_utc(start_text)
    end = parse_utc(end_text)
    if not (start <= now() <= end):
        return "clock is outside the approved window"
    return ""


def _deploy_environment(
    state: dict[str, Any], members: list[dict[str, Any]], environment: str
) -> str:
    ctx = current()
    outcomes: list[str] = []
    deployed_threads: list[tuple[str, str]] = []
    for member in members:
        for ci_name in member.get("ci_names") or []:
            if str(ci_name).startswith("SYN "):
                continue
            sim_thread = f"{state['thread_id']}|{ci_name}|{environment}"
            deployed = run_deploy(
                default_path(),
                thread_id=sim_thread,
                ci=str(ci_name),
                environment=environment,
                strategy="big bang",
                version=str(state.get("change_number") or ""),
                fail_at=None,
            )
            if not deployed.get("replayed"):
                for step in deployed["steps"]:
                    record_audit(
                        thread_id=state["thread_id"],
                        agent="deployment",
                        action="deploy_step",
                        record=str(state.get("change_number") or ""),
                        outcome=(
                            f"env={environment} ci={ci_name} "
                            f"step={step['step']} result={step['result']}"
                        ),
                    )
            verified = deployed["outcome"] == "verified" and passes_thresholds(
                deployed["before"], deployed["after"], ctx.policy
            )
            outcomes.append("verified" if verified else "failed")
            deployed_threads.append((sim_thread, str(ci_name)))
            if not verified:
                _rollback_stage(state, environment, deployed_threads)
                _record_stage(ctx.client, state, environment, "failed")
                return "failed"
    if not outcomes:
        _record_stage(ctx.client, state, environment, "failed")
        return "failed"
    _record_stage(ctx.client, state, environment, "passed")
    return "passed"


def _rollback_stage(
    state: dict[str, Any], environment: str, deployed: list[tuple[str, str]]
) -> None:
    for sim_thread, ci_name in deployed:
        rolled = run_rollback(
            default_path(),
            thread_id=sim_thread,
            ci=ci_name,
            environment=environment,
            fail=False,
        )
        record_audit(
            thread_id=state["thread_id"],
            agent="deployment",
            action="rollback",
            record=str(state.get("change_number") or ""),
            outcome=f"env={environment} ci={ci_name} result={rolled['outcome']}",
        )


def _record_stage(
    client: ServiceNowClient, state: dict[str, Any], environment: str, result: str
) -> None:
    task = ensure_change_task(
        client,
        state["change_sys_id"],
        short_description=implementation_task_name(environment),
        task_type="implementation",
    )
    client.update_record(
        "change_task",
        str(task["sys_id"]),
        {"description": f"result={result}", "close_notes": f"result={result}"},
    )
    close_change_task(client, str(task["sys_id"]))
    stored = client.get_record(
        "change_task",
        str(task["sys_id"]),
        fields=["description", "close_notes", "state"],
    )
    blob = f"{stored.get('description') or ''} {stored.get('close_notes') or ''}"
    if f"result={result}" not in blob:
        raise ChangeError(f"{environment} stage result did not stick")
    write_note(
        client,
        state["change_sys_id"],
        thread_id=state["thread_id"],
        agent="deployment",
        decision="stage",
        reason=f"{environment} result={result}",
        record=str(state.get("change_number") or ""),
    )


def _close_member(
    client: ServiceNowClient,
    member: dict[str, Any],
    release_number: str,
    release_summary_text: str,
) -> None:
    sys_id = str(member["sys_id"])
    record = read_change(client, sys_id)
    if str(record.get("state") or "") == STATE_CLOSED:
        notes = str(record.get("close_notes") or "")
        if release_number not in notes:
            raise ChangeError(f"{record.get('number')} closed without the release number")
        return
    if str(record.get("state") or "") == STATE_SCHEDULED:
        record = move_state(client, "normal", sys_id, STATE_IMPLEMENT)
    if str(record.get("state") or "") == STATE_IMPLEMENT:
        record = move_state(client, "normal", sys_id, STATE_REVIEW)
    if str(record.get("state") or "") != STATE_REVIEW:
        raise ChangeError(f"{record.get('number')} could not be moved to Review")
    note = member_close_note(release_number, release_summary_text)
    update_fields(client, sys_id, {"close_code": "successful", "close_notes": note})
    closed = move_state(client, "normal", sys_id, STATE_CLOSED)
    if str(closed.get("state") or "") != STATE_CLOSED:
        raise ChangeError(f"{closed.get('number')} did not close")
    if str(closed.get("close_code") or "") != "successful":
        raise ChangeError(f"{closed.get('number')} close_code is {closed.get('close_code')}")
    if release_number not in str(closed.get("close_notes") or ""):
        raise ChangeError(f"{closed.get('number')} close notes do not name the release")
    tasks = client.get_table(
        "change_task",
        query=f"change_request={sys_id}",
        fields=["sys_id", "short_description"],
        limit=20,
    )
    unexpected = unexpected_change_tasks(tasks)
    if unexpected:
        joined = ", ".join(unexpected)
        raise ChangeError(f"{closed.get('number')} has an unexpected change task: {joined}")


def _release_close_notes(state: dict[str, Any], number: str) -> str:
    stages = (state.get("deployment") or {}).get("stages") or []
    lines = [f"release {number}"]
    for stage in stages:
        lines.append(f"{stage.get('environment')} {stage.get('result')}")
    draft = complete(
        current().settings,
        CloseNotes,
        system="Summarize this release deployment in close notes. Make no decision.",
        user=record_block("\n".join(lines)),
        thread_id=state["thread_id"],
        agent="release",
        action="close_notes",
        record=number,
    )
    return draft.close_notes.strip()[:4000]


def _stamp(client: ServiceNowClient, change_id: str, field: str) -> None:
    record = read_change(client, change_id)
    if str(record.get(field) or ""):
        return
    stamp = now().astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
    update_fields(client, change_id, {field: stamp})
