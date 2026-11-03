"""Move an authorized change through Implement and the simulator.

The approved planned window is the deployment window. Policy code, not
ServiceNow's not_in_maintenance_window flag, decides whether that window is a
maintenance window. A failed PROD deploy is never run again.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from pydantic import BaseModel

from cm_agents.agents.context import current
from cm_agents.audit import record_audit
from cm_agents.clock import now
from cm_agents.data.import_time import UTC, parse_utc
from cm_agents.deploy.simulator import (
    HEALTHY,
    RedeployBlocked,
    agent_outcome,
    block_prod,
    default_path,
    passes_thresholds,
    run_deploy,
    run_rollback,
    set_agent_outcome,
)
from cm_agents.enablement.windows import deployment_blocked_by_policy
from cm_agents.llm import complete
from cm_agents.servicenow.changes import (
    STATE_IMPLEMENT,
    STATE_REVIEW,
    STATE_SCHEDULED,
    ChangeError,
    close_change_task,
    ensure_change_task,
    find_incident,
    move_state,
    read_change,
    remember_row,
    update_fields,
    write_note,
)
from cm_agents.servicenow.client import ServiceNowClient


class CloseNotes(BaseModel):
    close_notes: str


def run_deployment(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("error"):
        return {}
    done = state.get("deployment") or {}
    if done.get("outcome") in {"verified", "rolled_back", "rollback_failed", "blocked"}:
        return {}
    ctx = current()
    record = read_change(ctx.client, state["change_sys_id"])
    blocked = _precondition(state, record)
    if blocked:
        _note(state, "blocked", blocked)
        return {
            "error": blocked,
            "deployment": {"outcome": "blocked", "change_state": str(record.get("state") or "")},
        }
    if str(record.get("state") or "") == STATE_SCHEDULED:
        record = _move(ctx.client, state["change_type"], state["change_sys_id"], STATE_IMPLEMENT)
    environment = _environment(ctx.fixtures, state)
    _stamp(ctx.client, state["change_sys_id"], "work_start")
    tasks = _ensure_tasks(ctx.client, state["change_sys_id"], environment)
    ci_name = _ci_name(state)
    fail_at = state.get("request", {}).get("fail_at")
    if not isinstance(fail_at, dict):
        fail_at = None
    try:
        deployed = run_deploy(
            default_path(),
            thread_id=state["thread_id"],
            ci=ci_name,
            environment=environment,
            strategy=str(state.get("request", {}).get("deployment_strategy") or "big bang"),
            version=str(state.get("change_number") or record.get("number") or ""),
            fail_at=fail_at,
        )
    except RedeployBlocked as exc:
        record_audit(
            thread_id=state["thread_id"],
            agent="deployment",
            action="deploy_step",
            record=str(state.get("change_number") or ""),
            outcome=f"env={environment} step=blocked result=blocked",
        )
        return {
            "error": str(exc),
            "deployment": {"outcome": "blocked", "change_state": STATE_IMPLEMENT},
        }
    if not deployed.get("replayed"):
        for step in deployed["steps"]:
            record_audit(
                thread_id=state["thread_id"],
                agent="deployment",
                action="deploy_step",
                record=str(state.get("change_number") or ""),
                outcome=(
                    f"env={deployed['environment']} step={step['step']} result={step['result']}"
                ),
            )
    decided = agent_outcome(default_path(), state["thread_id"])
    if not decided:
        verified = deployed["outcome"] == "verified" and passes_thresholds(
            deployed["before"], deployed["after"], ctx.policy
        )
        fresh = _fresh_incidents(ctx.client, state) if verified else []
        decided = "verified" if verified and not fresh else "failed"
        if decided == "failed":
            block_prod(default_path(), ci_name, environment)
        set_agent_outcome(default_path(), state["thread_id"], decided)
    if decided == "verified":
        _close_tasks(ctx.client, tasks)
        _stamp(ctx.client, state["change_sys_id"], "work_end")
        record = _move(ctx.client, state["change_type"], state["change_sys_id"], STATE_REVIEW)
        notes = _summarize(state, deployed, "verified")
        _note(state, "verified", "deployment met the verification thresholds")
        return {
            "deployment": {
                "outcome": "verified",
                "close_notes": notes,
                "change_state": str(record.get("state") or ""),
                "incident": "",
                "priority": "",
                "environment": environment,
            }
        }
    rollback_injected = bool(fail_at) and str(fail_at.get("step") or "") == "rollback"
    rolled = run_rollback(
        default_path(),
        thread_id=state["thread_id"],
        ci=ci_name,
        environment=environment,
        fail=rollback_injected and str(fail_at.get("env") or "").upper() == environment,
    )
    if not rolled.get("replayed"):
        record_audit(
            thread_id=state["thread_id"],
            agent="deployment",
            action="rollback",
            record=str(state.get("change_number") or ""),
            outcome=f"env={environment} result={rolled['outcome']}",
        )
    rollback_ok = rolled["outcome"] == "rolled_back" and passes_thresholds(
        HEALTHY, rolled["after"], ctx.policy
    )
    if not rollback_ok:
        _note(state, "rollback_failed", "rollback did not verify; a human has to take the change")
        left = read_change(ctx.client, state["change_sys_id"])
        return {
            "deployment": {
                "outcome": "rollback_failed",
                "change_state": str(left.get("state") or ""),
                "environment": environment,
            }
        }
    incident = _ensure_incident(ctx, state, record)
    _close_tasks(ctx.client, tasks)
    _stamp(ctx.client, state["change_sys_id"], "work_end")
    record = _move(ctx.client, state["change_type"], state["change_sys_id"], STATE_REVIEW)
    notes = _summarize(state, deployed, "rolled_back")
    _note(
        state,
        "rolled_back",
        f"verification failed, rollback verified, incident {incident.get('number')}",
    )
    return {
        "deployment": {
            "outcome": "rolled_back",
            "close_notes": notes,
            "change_state": str(record.get("state") or ""),
            "incident": str(incident.get("number") or ""),
            "incident_sys_id": str(incident.get("sys_id") or ""),
            "priority": str(incident.get("priority") or ""),
            "impact": str(incident.get("impact") or ""),
            "urgency": str(incident.get("urgency") or ""),
            "environment": environment,
        }
    }


def _precondition(state: dict[str, Any], record: dict[str, Any]) -> str:
    change_type = str(state.get("change_type") or "")
    current_state = str(record.get("state") or "")
    if change_type == "normal" and not state.get("release_member"):
        decision = ((state.get("authorization") or {}).get("go_no_go") or {}).get("decision")
        if decision != "go":
            return "normal change has no go decision"
    if current_state not in {STATE_SCHEDULED, STATE_IMPLEMENT}:
        return "change is not Scheduled"
    if current_state != STATE_SCHEDULED:
        return ""
    start_text = str(record.get("start_date") or "")
    end_text = str(record.get("end_date") or "")
    if not start_text or not end_text:
        return "approved window is missing"
    start = parse_utc(start_text)
    end = parse_utc(end_text)
    moment = now()
    if not (start <= moment <= end):
        return "clock is outside the approved window"
    tier = int(state.get("service_tier") or 3)
    if deployment_blocked_by_policy(change_type, start, end, tier):
        return "standard change is outside the policy maintenance window"
    return ""


def _environment(fixtures: dict[str, Any], state: dict[str, Any]) -> str:
    by_name = {row["name"]: row for row in fixtures["cis"]}
    for row in state.get("affected_cis") or []:
        env = str(by_name.get(row["name"], {}).get("environment") or "").lower()
        if env:
            return "PROD" if env == "prod" else env.upper()
    return "PROD"


def _ci_name(state: dict[str, Any]) -> str:
    rows = list(state.get("affected_cis") or [])
    if not rows:
        raise ChangeError("deployment has no affected CI")
    return str(rows[0]["name"])


def _ensure_tasks(
    client: ServiceNowClient, change_id: str, environment: str
) -> list[dict[str, Any]]:
    tasks = []
    for task_type in ("implementation", "testing"):
        tasks.append(
            ensure_change_task(
                client,
                change_id,
                short_description=f"SYN {environment} {task_type}",
                task_type=task_type,
            )
        )
    return tasks


def _close_tasks(client: ServiceNowClient, tasks: list[dict[str, Any]]) -> None:
    for task in tasks:
        current_state = str(task.get("state") or "")
        if current_state == "3":
            continue
        closed = close_change_task(client, str(task["sys_id"]))
        if str(closed.get("state") or "") != "3":
            raise ChangeError(f"change task state is {closed.get('state')} after close")


def _fresh_incidents(client: ServiceNowClient, state: dict[str, Any]) -> list[dict[str, Any]]:
    minutes = int(current().policy["verification"]["window_minutes"])
    end = now()
    start = end - timedelta(minutes=minutes)
    start_text = start.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
    end_text = end.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
    found: list[dict[str, Any]] = []
    for row in state.get("affected_cis") or []:
        rows = client.get_table(
            "incident",
            query=(
                f"cmdb_ci={row['sys_id']}^opened_at>={start_text}^opened_at<={end_text}"
                f"^correlation_id!={state['thread_id']}"
            ),
            fields=["sys_id", "number", "priority", "correlation_id"],
            limit=10,
        )
        found.extend(rows)
    return found


def _ensure_incident(ctx: Any, state: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    existing = find_incident(ctx.client, state["thread_id"])
    if existing:
        return existing
    tier = int(state.get("service_tier") or 3)
    impact, urgency = {1: ("1", "1"), 2: ("2", "2"), 3: ("3", "3")}.get(tier, ("3", "3"))
    ci_id = str((state.get("affected_cis") or [{}])[0].get("sys_id") or "")
    number = str(state.get("change_number") or record.get("number") or "")
    created = ctx.client.create_record(
        "incident",
        {
            "short_description": f"SYN deployment failed {number}",
            "description": "Verification failed and the deployment was rolled back.",
            "correlation_id": state["thread_id"],
            "u_caused_by": state["change_sys_id"],
            "cmdb_ci": ci_id,
            "impact": impact,
            "urgency": urgency,
        },
    )
    stored = ctx.client.get_record(
        "incident",
        str(created["sys_id"]),
        fields=[
            "sys_id",
            "number",
            "priority",
            "impact",
            "urgency",
            "u_caused_by",
            "correlation_id",
        ],
    )
    if str(stored.get("u_caused_by") or "") != state["change_sys_id"]:
        raise ChangeError("incident.u_caused_by did not keep the change")
    remember_row("incident", str(stored["sys_id"]), state["thread_id"])
    return stored


def _summarize(state: dict[str, Any], deployed: dict[str, Any], outcome: str) -> str:
    lines = [
        f"outcome {outcome}",
        f"environment {deployed['environment']}",
        f"strategy result {deployed['outcome']}",
    ]
    for step in deployed["steps"]:
        signals = step["signals"]
        lines.append(
            f"{step['step']} {step['result']} error_rate_pct {signals['error_rate_pct']} "
            f"p95_latency_ms {signals['p95_latency_ms']} "
            f"availability_pct {signals['availability_pct']}"
        )
    draft = complete(
        current().settings,
        CloseNotes,
        system="Summarize this deployment log in close notes. Make no decision.",
        user="\n".join(lines),
        thread_id=state["thread_id"],
        agent="deployment",
        action="close_notes",
        record=str(state.get("change_number") or ""),
    )
    return draft.close_notes.strip()[:4000]


def _stamp(client: ServiceNowClient, change_id: str, field: str) -> None:
    record = read_change(client, change_id)
    if str(record.get(field) or ""):
        return
    stamp = now().astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
    update_fields(client, change_id, {field: stamp})


def _move(client: ServiceNowClient, kind: str, change_id: str, target: str) -> dict[str, Any]:
    record = move_state(client, kind, change_id, target)
    if str(record.get("state") or "") != target:
        raise ChangeError(f"state is {record.get('state')} after a move to {target}")
    return record


def _note(state: dict[str, Any], decision: str, reason: str) -> None:
    from cm_agents.servicenow.changes import journal

    marker = f"[agent:deployment] {decision}:"
    if any(marker in text for text in journal(current().client, state["change_sys_id"])):
        return
    write_note(
        current().client,
        state["change_sys_id"],
        thread_id=state["thread_id"],
        agent="deployment",
        decision=decision,
        reason=reason,
        record=str(state.get("change_number") or ""),
    )


