"""Change API and Table API calls used by the enablement agents.

Affected CIs are added with POST /api/sn_chg_rest/change/{sys_id}/ci while the
change is still New. A Table API insert into task_ci is blocked on this PDI.
"""

from __future__ import annotations

import re
import time
from typing import Any

from cm_agents.audit import record_audit
from cm_agents.data.manifest import add_record, load_manifest, save_manifest
from cm_agents.servicenow.client import ServiceNowClient, ServiceNowError
from cm_agents.settings import repo_root

STATE_NEW = "-5"
STATE_ASSESS = "-4"
STATE_AUTHORIZE = "-3"
STATE_SCHEDULED = "-2"
STATE_IMPLEMENT = "-1"
STATE_REVIEW = "0"
STATE_CLOSED = "3"

_SYS_ID = re.compile(r"^[0-9a-f]{32}$")
_READ_FIELDS = [
    "sys_id",
    "number",
    "state",
    "type",
    "approval",
    "risk",
    "impact",
    "cmdb_ci",
    "assignment_group",
    "start_date",
    "end_date",
    "correlation_id",
    "short_description",
    "parent",
    "active",
    "work_start",
    "work_end",
    "close_code",
    "close_notes",
]


class ChangeError(RuntimeError):
    """A ServiceNow write did not stick. The thread can be resumed."""


def remember_change(sys_id: str, key: str) -> None:
    remember_row("change_request", sys_id, key)


def remember_row(table: str, sys_id: str, key: str) -> None:
    path = repo_root() / "data" / "synthetic" / "manifest.json"
    manifest = load_manifest(path)
    if manifest is None:
        return
    add_record(manifest, table, sys_id, key)
    save_manifest(path, manifest)


def find_by_correlation(client: ServiceNowClient, thread_id: str) -> dict[str, Any] | None:
    rows = client.get_table(
        "change_request",
        query=f"correlation_id={thread_id}",
        fields=_READ_FIELDS,
        limit=2,
    )
    if len(rows) > 1:
        raise ChangeError(f"more than one change uses correlation_id {thread_id}")
    return rows[0] if rows else None


def read_change(client: ServiceNowClient, sys_id: str) -> dict[str, Any]:
    return client.get_record("change_request", sys_id, fields=_READ_FIELDS)


def create_change(client: ServiceNowClient, kind: str, body: dict[str, Any]) -> dict[str, Any]:
    path = f"/api/sn_chg_rest/change/{kind}"
    payload = client.request("POST", path, json=body)
    sys_id = _field(payload, "sys_id")
    if not sys_id:
        found = find_by_correlation(client, str(body.get("correlation_id") or ""))
        if found:
            return found
        raise ChangeError(f"create {kind} did not return a sys_id")
    return read_change(client, sys_id)


def create_standard(
    client: ServiceNowClient, template_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    payload = client.request(
        "POST", f"/api/sn_chg_rest/change/standard/{template_id}", json=body
    )
    sys_id = _field(payload, "sys_id")
    if not sys_id:
        found = find_by_correlation(client, str(body.get("correlation_id") or ""))
        if found:
            return found
        raise ChangeError("create standard did not return a sys_id")
    return read_change(client, sys_id)


def update_fields(client: ServiceNowClient, sys_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    client.update_record("change_request", sys_id, fields)
    return read_change(client, sys_id)


def write_note(
    client: ServiceNowClient,
    sys_id: str,
    *,
    thread_id: str,
    agent: str,
    decision: str,
    reason: str,
    record: str,
) -> None:
    text = f"[agent:{agent}] {decision}: {reason}"
    client.update_record("change_request", sys_id, {"work_notes": text})
    record_audit(
        thread_id=thread_id,
        agent=agent,
        action=decision,
        record=record,
        outcome=reason[:500],
    )


def attach_affected(client: ServiceNowClient, change_id: str, ci_ids: list[str]) -> None:
    """Add affected CIs through the Change API. The worker must finish first."""
    existing = {
        str(row.get("ci_item") or "")
        for row in client.get_table(
            "task_ci",
            query=f"task={change_id}",
            fields=["ci_item"],
            limit=50,
        )
    }
    missing = [ci_id for ci_id in ci_ids if ci_id not in existing]
    if not missing:
        return
    payload = client.request(
        "POST",
        f"/api/sn_chg_rest/change/{change_id}/ci",
        json={"cmdb_ci_sys_ids": ",".join(missing), "association_type": "affected"},
    )
    worker = _worker_id(payload)
    if worker:
        _wait_worker(client, worker)
    linked = client.get_table(
        "task_ci",
        query=f"task={change_id}",
        fields=["ci_item"],
        limit=50,
    )
    found = {str(row.get("ci_item") or "") for row in linked}
    absent = [ci_id for ci_id in ci_ids if ci_id not in found]
    if absent:
        raise ChangeError("Change API did not store every affected CI")


def move_state(client: ServiceNowClient, kind: str, sys_id: str, state: str) -> dict[str, Any]:
    client.request(
        "PATCH",
        f"/api/sn_chg_rest/change/{kind}/{sys_id}",
        json={"state": state},
    )
    return read_change(client, sys_id)


def write_dates(
    client: ServiceNowClient, sys_id: str, start: str, end: str
) -> dict[str, Any]:
    """Table API dates with display_value=false are UTC on this instance."""
    updated = update_fields(client, sys_id, {"start_date": start, "end_date": end})
    if updated.get("start_date") != start or updated.get("end_date") != end:
        raise ChangeError(
            "planned dates read back "
            f"{updated.get('start_date')} {updated.get('end_date')} after writing {start} {end}"
        )
    return updated


def write_risk(client: ServiceNowClient, sys_id: str, risk: str, impact: str) -> dict[str, Any]:
    updated = update_fields(client, sys_id, {"risk": risk, "impact": impact})
    if str(updated.get("risk") or "") != risk or str(updated.get("impact") or "") != impact:
        raise ChangeError(
            "risk read back "
            f"{updated.get('risk')}/{updated.get('impact')} after writing {risk}/{impact}"
        )
    return updated


def link_service(client: ServiceNowClient, change_id: str, service_id: str) -> str:
    """Insert task_cmdb_ci_service. Returns 'linked' or 'forbidden'."""
    try:
        rows = client.get_table(
            "task_cmdb_ci_service",
            query=f"task={change_id}^cmdb_ci_service={service_id}",
            fields=["sys_id"],
            limit=1,
        )
    except ServiceNowError as exc:
        if exc.status_code in {401, 403}:
            return "forbidden"
        raise
    if rows:
        return "linked"
    try:
        client.create_record(
            "task_cmdb_ci_service",
            {"task": change_id, "cmdb_ci_service": service_id},
        )
    except ServiceNowError as exc:
        if exc.status_code in {401, 403}:
            return "forbidden"
        raise
    return "linked"


def conflicts_for(client: ServiceNowClient, change_id: str) -> tuple[list[dict[str, Any]], str]:
    """Return conflict rows and 'ok' or 'unreadable'.

    The check is a worker. The table is read until the row set stops growing
    so a maintenance row does not hide a later CI schedule row.
    """
    try:
        payload = client.request(
            "POST", f"/api/sn_chg_rest/change/{change_id}/conflict", json={}
        )
    except ServiceNowError as exc:
        if exc.status_code in {401, 403, 400, 404}:
            return [], "unreadable"
        raise
    worker = _worker_id(payload)
    if worker:
        try:
            _wait_worker(client, worker)
        except ChangeError:
            pass
    last: list[dict[str, Any]] = []
    for _ in range(6):
        try:
            rows = client.get_table(
                "conflict",
                query=f"change={change_id}",
                fields=["sys_id", "type", "change", "conflicting_change"],
                limit=20,
            )
        except ServiceNowError as exc:
            if exc.status_code in {401, 403, 400, 404}:
                return [], "unreadable"
            raise
        same = {str(row.get("sys_id") or "") for row in rows} == {
            str(row.get("sys_id") or "") for row in last
        }
        last = rows
        if rows and same:
            return rows, "ok"
        time.sleep(2)
    return last, "ok"


def approvals_for(client: ServiceNowClient, change_id: str) -> list[dict[str, Any]]:
    return client.get_table(
        "sysapproval_approver",
        query=f"sysapproval={change_id}",
        fields=["sys_id", "state", "approver", "group", "sys_updated_by", "sys_mod_count"],
        limit=40,
    )


def approval_groups_for(client: ServiceNowClient, change_id: str) -> list[dict[str, Any]]:
    return client.get_table(
        "sysapproval_group",
        query=f"parent={change_id}",
        fields=["sys_id", "assignment_group", "approval"],
        limit=10,
    )


def exact_ci(client: ServiceNowClient, name: str) -> list[dict[str, Any]]:
    return client.get_table(
        "cmdb_ci",
        query=f"name={name}",
        fields=["sys_id", "name", "sys_class_name"],
        limit=5,
    )


def containing_cis(client: ServiceNowClient, text: str) -> list[dict[str, Any]]:
    return client.get_table(
        "cmdb_ci",
        query=f"nameLIKE{text}",
        fields=["sys_id", "name", "sys_class_name"],
        limit=20,
    )


def group_id(client: ServiceNowClient, name: str) -> str:
    rows = client.get_table(
        "sys_user_group",
        query=f"name={name}",
        fields=["sys_id", "name"],
        limit=2,
    )
    match = [row for row in rows if row.get("name") == name]
    if len(match) != 1:
        raise ChangeError(f"assignment group {name} was not found")
    return str(match[0]["sys_id"])


def group_name(client: ServiceNowClient, sys_id: str) -> str:
    if not sys_id:
        return ""
    record = client.get_record("sys_user_group", sys_id, fields=["name"])
    return str(record.get("name") or "")


def service_ci(client: ServiceNowClient, name: str) -> str:
    rows = client.get_table(
        "cmdb_ci_service",
        query=f"name={name}",
        fields=["sys_id", "name"],
        limit=2,
    )
    match = [row for row in rows if row.get("name") == name]
    if len(match) != 1:
        return ""
    return str(match[0]["sys_id"])


def template_id(client: ServiceNowClient, name: str) -> str:
    rows = client.get_table(
        "std_change_record_producer",
        query=f"name={name}",
        fields=["sys_id", "name"],
        limit=2,
    )
    match = [row for row in rows if row.get("name") == name]
    return str(match[0]["sys_id"]) if len(match) == 1 else ""


def find_incident(client: ServiceNowClient, token: str) -> dict[str, Any] | None:
    query = f"number={token}^ORcorrelation_id={token}"
    rows = client.get_table(
        "incident",
        query=query,
        fields=["sys_id", "number", "state", "priority", "cmdb_ci", "short_description"],
        limit=2,
    )
    return rows[0] if len(rows) == 1 else None


def find_release(client: ServiceNowClient, summary: str) -> str:
    rows = client.get_table(
        "change_request",
        query=f"short_description={summary}",
        fields=["sys_id", "short_description"],
        limit=2,
    )
    match = [row for row in rows if row.get("short_description") == summary]
    return str(match[0]["sys_id"]) if len(match) == 1 else ""


def active_on_ci(client: ServiceNowClient, ci_id: str, change_id: str) -> list[dict[str, str]]:
    """Planned windows of other active changes whose primary CI is this CI."""
    rows = client.get_table(
        "change_request",
        query=f"cmdb_ci={ci_id}^active=true^sys_id!={change_id}",
        fields=["sys_id", "number", "start_date", "end_date", "state"],
        limit=30,
    )
    windows = []
    for row in rows:
        start = str(row.get("start_date") or "")
        end = str(row.get("end_date") or "")
        if start and end:
            windows.append({"start": start, "end": end, "number": str(row.get("number") or "")})
    return windows


def same_window(client: ServiceNowClient, change_id: str, start: str, end: str) -> list[str]:
    rows = client.get_table(
        "change_request",
        query=f"start_date<{end}^end_date>{start}^active=true^sys_id!={change_id}",
        fields=["number", "short_description"],
        limit=10,
    )
    return [
        f"{row.get('number')} {row.get('short_description')}".strip()
        for row in rows
        if row.get("number")
    ]


def approval_comments(client: ServiceNowClient, change_id: str) -> list[str]:
    """Approval comments are journal rows. The comments column stays empty."""
    approvers = client.get_table(
        "sysapproval_approver",
        query=f"sysapproval={change_id}",
        fields=["sys_id"],
        limit=40,
    )
    texts: list[str] = []
    for row in approvers:
        notes = client.get_table(
            "sys_journal_field",
            query=(
                "name=sysapproval_approver^element=comments"
                f"^element_id={row['sys_id']}"
            ),
            fields=["value"],
            limit=5,
        )
        for note in notes:
            value = str(note.get("value") or "").strip()
            if value:
                texts.append(value)
    return texts


def change_tasks(client: ServiceNowClient, change_id: str) -> list[dict[str, Any]]:
    return client.get_table(
        "change_task",
        query=f"change_request={change_id}",
        fields=[
            "sys_id",
            "number",
            "short_description",
            "change_task_type",
            "state",
            "description",
            "close_notes",
        ],
        limit=20,
    )


def ensure_change_task(
    client: ServiceNowClient,
    change_id: str,
    *,
    short_description: str,
    task_type: str,
) -> dict[str, Any]:
    for row in change_tasks(client, change_id):
        if (
            str(row.get("short_description") or "") == short_description
            and str(row.get("change_task_type") or "") == task_type
        ):
            return row
    created = client.create_record(
        "change_task",
        {
            "change_request": change_id,
            "short_description": short_description,
            "change_task_type": task_type,
        },
    )
    return created


def close_change_task(client: ServiceNowClient, task_id: str) -> dict[str, Any]:
    return client.update_record("change_task", task_id, {"state": "3"})


def journal(client: ServiceNowClient, change_id: str) -> list[str]:
    rows = client.get_table(
        "sys_journal_field",
        query=f"name=change_request^element=work_notes^element_id={change_id}",
        fields=["value"],
        limit=40,
    )
    return [str(row.get("value") or "") for row in rows]


def _wait_worker(client: ServiceNowClient, worker_id: str) -> None:
    last = ""
    for _ in range(8):
        payload = client.request("GET", f"/api/sn_chg_rest/change/worker/{worker_id}")
        result = payload.get("result") if isinstance(payload, dict) else None
        state = ""
        errors: list[object] = []
        if isinstance(result, dict):
            raw_state = result.get("state")
            if isinstance(raw_state, dict):
                state = str(raw_state.get("value") or "")
            else:
                state = str(raw_state or "")
            messages = result.get("messages")
            if isinstance(messages, dict):
                errors = list(messages.get("errorMessages") or [])
        last = state
        if errors:
            raise ChangeError("affected CI worker reported an error")
        if state == "3":
            return
        time.sleep(2)
    raise ChangeError(f"affected CI worker did not finish (state {last})")


def _worker_id(payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if isinstance(result, dict):
        worker = result.get("worker")
        if isinstance(worker, dict):
            for key in ("sysId", "sys_id"):
                value = worker.get(key)
                if isinstance(value, str) and _SYS_ID.fullmatch(value):
                    return value
    return ""


def _field(payload: dict[str, Any], name: str) -> str:
    result = payload.get("result")
    if isinstance(result, dict) and name in result:
        value = result[name]
        if isinstance(value, dict):
            inner = str(value.get("value") or "")
            if _SYS_ID.fullmatch(inner) or name == "number":
                return inner
        if isinstance(value, str) and (_SYS_ID.fullmatch(value) or name != "sys_id"):
            return value
    return ""
