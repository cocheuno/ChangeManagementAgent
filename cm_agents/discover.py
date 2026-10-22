"""Phase 0 discovery probes.

Read-only checks run first. A SYN-PROBE change is created only after outbound
email is confirmed disabled. Every probe record is deleted before returning.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import time
from typing import Any

from cm_agents.servicenow.client import ServiceNowClient, ServiceNowError
from cm_agents.settings import Settings, redact_text, repo_root

PROBE_MARKER = "SYN-PROBE"
PROBE_USER = "syn.probe.user"
_FALSE = {"false", "0", "no", "off"}
_TRUE = {"true", "1", "yes", "on"}
_SYS_ID_RE = re.compile(r"[0-9a-f]{32}")
_EXTRA_TABLES = frozenset(
    {
        "task_ci",
        "task_cmdb_ci_service",
        "sysapproval_approver",
        "change_task",
        "conflict",
        "sys_user_has_role",
    }
)
_extra_deletes: list[tuple[str, str]] = []
_extra_secrets: list[str] = []
_CHANGE_FIELDS = [
    "sys_id",
    "number",
    "state",
    "type",
    "risk",
    "impact",
    "urgency",
    "priority",
    "approval",
    "close_code",
    "close_notes",
    "opened_at",
    "closed_at",
    "work_start",
    "work_end",
    "start_date",
    "end_date",
    "short_description",
    "correlation_id",
    "chg_model",
    "conflict_status",
    "assignment_group",
    "cmdb_ci",
    "risk_impact_analysis",
]


def evaluate_outbound_email(
    properties: dict[str, str],
    active_email_accounts: int | None,
) -> tuple[bool, str]:
    """Return whether it is safe to create a SYN-PROBE change, and why."""
    raw = properties.get("glide.email.smtp.active")
    if raw is None:
        return False, "glide.email.smtp.active was not found. SYN-PROBE was not created."
    normalized = raw.strip().lower()
    if normalized in _TRUE:
        return False, "glide.email.smtp.active is true. SYN-PROBE was not created."
    if normalized not in _FALSE:
        return False, (
            "glide.email.smtp.active is not a clear false value. SYN-PROBE was not created."
        )
    if active_email_accounts is None:
        return False, "sys_email_account could not be read. SYN-PROBE was not created."
    if active_email_accounts > 0:
        return False, (
            f"{active_email_accounts} active email accounts exist. SYN-PROBE was not created."
        )
    return True, "glide.email.smtp.active is false and no active email account exists."


def residue_queries() -> list[tuple[str, str]]:
    marker = PROBE_MARKER
    return [
        (
            "change_request",
            f"short_descriptionSTARTSWITH{marker}^ORcorrelation_id={marker}",
        ),
        (
            "change_task",
            "short_descriptionSTARTSWITH"
            f"{marker}^ORparent.short_descriptionSTARTSWITH{marker}"
            f"^ORchange_request.short_descriptionSTARTSWITH{marker}",
        ),
        ("task_ci", f"task.short_descriptionSTARTSWITH{marker}"),
        ("task_cmdb_ci_service", f"task.short_descriptionSTARTSWITH{marker}"),
        ("sysapproval_approver", f"sysapproval.short_descriptionSTARTSWITH{marker}"),
        ("sysapproval_group", f"parent.short_descriptionSTARTSWITH{marker}"),
        (
            "conflict",
            "change.short_descriptionSTARTSWITH"
            f"{marker}^ORconflicting_change.short_descriptionSTARTSWITH{marker}",
        ),
        ("sys_user", f"first_name={marker}^ORuser_name={PROBE_USER}"),
        ("sys_user_has_role", f"user.user_name={PROBE_USER}"),
        ("cmn_schedule_blackout", f"nameSTARTSWITH{marker}"),
        ("cmn_schedule", f"nameSTARTSWITH{marker}"),
    ]


def probe_role_query(user_id: str) -> str:
    """Direct role grants only. Inherited contained roles are not deleted."""
    return f"user={user_id}^inherited=false"


def run_discover(settings: Settings) -> int:
    _extra_deletes.clear()
    _extra_secrets.clear()
    evidence: dict[str, Any] = {}
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
    ) as client:
        proceed, message, email_evidence = _email_gate(client)
        evidence["email"] = email_evidence
        print(message)
        if not proceed:
            _write_evidence(evidence, settings)
            return 2
        failed = False
        try:
            _cleanup(client)
            _probe_changes(client, evidence)
            _probe_user(client, settings, evidence)
        except Exception as exc:
            failed = True
            evidence["probe_error"] = redact_text(
                str(exc),
                [*settings.secret_values(), *_extra_secrets],
            )
            print(f"discovery probe failed: {type(exc).__name__}")
        finally:
            _cleanup(client)
            evidence["residue"] = _residue(client)
            _write_evidence(evidence, settings)
            _print_residue(evidence["residue"])
    dirty = any(item.get("count") != 0 for item in evidence["residue"])
    return 1 if failed or dirty else 0


def _email_gate(client: ServiceNowClient) -> tuple[bool, str, dict[str, Any]]:
    properties: dict[str, str] = {}
    try:
        rows = client.get_table(
            "sys_properties",
            query="nameINglide.email.smtp.active,glide.email.read.active",
            fields=["name", "value"],
            limit=10,
        )
        properties = {str(row.get("name")): str(row.get("value") or "") for row in rows}
    except ServiceNowError as exc:
        message = "Email properties could not be read. SYN-PROBE was not created."
        return False, message, {"error": str(exc), "status": exc.status_code}
    active_accounts: int | None
    try:
        accounts = client.get_table(
            "sys_email_account",
            query="active=true",
            fields=["name", "active", "type"],
            limit=20,
        )
        active_accounts = len(accounts)
    except ServiceNowError as exc:
        active_accounts = None
        account_error = {"error": str(exc), "status": exc.status_code}
    else:
        account_error = None
    proceed, message = evaluate_outbound_email(properties, active_accounts)
    return proceed, message, {
        "properties": properties,
        "active_email_accounts": active_accounts,
        "account_error": account_error,
        "proceed": proceed,
    }


def _probe_changes(client: ServiceNowClient, evidence: dict[str, Any]) -> None:
    evidence["normal"] = _create_change(client, "normal", "/api/sn_chg_rest/change/normal")
    normal_id = evidence["normal"].get("sys_id")
    if normal_id:
        evidence["risk"] = _risk_probe(client, normal_id)
        evidence["dates"] = _date_probe(client, normal_id)
        evidence["normal_transitions"] = _transition_probe(client, normal_id, "normal")
        evidence["normal_approvals"] = _approvals(client, normal_id)
    evidence["emergency"] = _create_change(
        client, "emergency", "/api/sn_chg_rest/change/emergency"
    )
    emergency_id = evidence["emergency"].get("sys_id")
    if emergency_id:
        evidence["emergency_transitions"] = _transition_probe(client, emergency_id, "emergency")
        evidence["emergency_approvals"] = _approvals(client, emergency_id)
    evidence["standard"] = _create_standard(client)
    standard_id = evidence["standard"].get("sys_id")
    if standard_id:
        evidence["standard_transitions"] = _transition_probe(client, standard_id, "standard")
        evidence["standard_approvals"] = _approvals(client, standard_id)
    evidence["historical"] = _historical_insert(client)
    evidence["conflict"] = _conflict_probe(client)
    evidence["blackout"] = _blackout_probe(client)


def _create_change(client: ServiceNowClient, kind: str, path: str) -> dict[str, Any]:
    body = {
        "short_description": f"{PROBE_MARKER} {kind}",
        "description": f"{PROBE_MARKER} discovery probe",
        "correlation_id": PROBE_MARKER,
    }
    created = _call(client, "POST", path, body)
    sys_id = _validated_sys_id(created)
    record = _read_change(client, sys_id) if sys_id else None
    print(f"create {kind}: sys_id_found={bool(sys_id)} http={created.get('status', 200)}")
    return {"request": created, "sys_id": sys_id, "record": record}


def _create_standard(client: ServiceNowClient) -> dict[str, Any]:
    templates = client.get_table(
        "std_change_record_producer",
        query="name=Replace printer toner",
        fields=["sys_id", "name"],
        limit=1,
    )
    if not templates:
        print("create standard: template not found")
        return {"error": "template Replace printer toner was not found"}
    template_id = str(templates[0]["sys_id"])
    created = _call(
        client,
        "POST",
        f"/api/sn_chg_rest/change/standard/{template_id}",
        {
            "short_description": f"{PROBE_MARKER} standard",
            "description": f"{PROBE_MARKER} discovery probe",
            "correlation_id": PROBE_MARKER,
        },
    )
    sys_id = _validated_sys_id(created)
    record = _read_change(client, sys_id) if sys_id else None
    print(f"create standard: sys_id_found={bool(sys_id)}")
    return {
        "template": templates[0].get("name"),
        "request": created,
        "sys_id": sys_id,
        "record": record,
    }


def _risk_probe(client: ServiceNowClient, sys_id: str) -> dict[str, Any]:
    before = _read_change(client, sys_id)
    # A far-future window avoids the "insufficient lead time" rule, and no CI is
    # set, so a recalculation should land on Low if it overwrites this High value.
    _call(
        client,
        "PATCH",
        f"/api/now/table/change_request/{sys_id}",
        {"start_date": "2026-12-15 02:00:00", "end_date": "2026-12-15 04:00:00"},
    )
    write = _call(
        client,
        "PATCH",
        f"/api/now/table/change_request/{sys_id}",
        {"risk": "2", "impact": "1"},
    )
    after_write = _read_change(client, sys_id)
    _call(
        client,
        "PATCH",
        f"/api/now/table/change_request/{sys_id}",
        {"short_description": f"{PROBE_MARKER} normal updated"},
    )
    after_other_update = _read_change(client, sys_id)
    calculate = _call(client, "PATCH", f"/api/sn_chg_rest/change/{sys_id}/risk", {})
    after_calculate = _read_change(client, sys_id)
    print(
        "risk:"
        f" before={_pair(before)} after_write={_pair(after_write)}"
        f" after_other={_pair(after_other_update)} after_calculate={_pair(after_calculate)}"
    )
    return {
        "before": before,
        "write": write,
        "after_write": after_write,
        "after_other_update": after_other_update,
        "calculate": calculate,
        "after_calculate": after_calculate,
    }


def _date_probe(client: ServiceNowClient, sys_id: str) -> dict[str, Any]:
    written = "2026-04-04 15:30:00"
    _call(
        client,
        "PATCH",
        f"/api/now/table/change_request/{sys_id}",
        {"start_date": written, "end_date": "2026-04-04 16:30:00"},
    )
    raw = _read_change(client, sys_id, display_value=False)
    displayed = _read_change(client, sys_id, display_value=True)
    print(f"dates: wrote {written} read {raw.get('start_date') if isinstance(raw, dict) else raw}")
    return {"wrote": written, "raw": raw, "display": displayed}


def _transition_probe(client: ServiceNowClient, sys_id: str, kind: str) -> dict[str, Any]:
    current = _read_change(client, sys_id)
    next_states = _call(client, "GET", f"/api/sn_chg_rest/change/{sys_id}/nextstates")
    illegal = _call(
        client,
        "PATCH",
        f"/api/now/table/change_request/{sys_id}",
        {"state": "3"},
    )
    after_illegal = _read_change(client, sys_id)
    allowed_value = "-4" if kind == "normal" else "-3"
    if kind == "standard":
        allowed_value = "-2"
    group_id = _named_group(client, "Change Management")
    group_write = None
    if group_id:
        group_write = _call(
            client,
            "PATCH",
            f"/api/now/table/change_request/{sys_id}",
            {"assignment_group": group_id},
        )
    allowed = _call(
        client,
        "PATCH",
        f"/api/sn_chg_rest/change/{kind}/{sys_id}",
        {"state": allowed_value},
    )
    if not allowed.get("ok"):
        allowed = _call(
            client,
            "PATCH",
            f"/api/now/table/change_request/{sys_id}",
            {"state": allowed_value},
        )
    after_allowed = _read_change(client, sys_id)
    state = after_allowed.get("state") if isinstance(after_allowed, dict) else None
    illegal_state = after_illegal.get("state") if isinstance(after_illegal, dict) else None
    if not _state_is(after_allowed, allowed_value):
        _fill_transition_fields(client, sys_id)
        allowed = _call(
            client,
            "PATCH",
            f"/api/sn_chg_rest/change/{kind}/{sys_id}",
            {"state": allowed_value},
        )
        if not allowed.get("ok"):
            allowed = _call(
                client,
                "PATCH",
                f"/api/now/table/change_request/{sys_id}",
                {"state": allowed_value},
            )
        after_allowed = _read_change(client, sys_id)
        state = after_allowed.get("state") if isinstance(after_allowed, dict) else None
    print(f"transition {kind}: illegal_left_state={illegal_state} now={state}")
    return {
        "before": current,
        "next_states": next_states,
        "illegal_close": illegal,
        "after_illegal": after_illegal,
        "assignment_group": "Change Management" if group_id else None,
        "assignment_group_write": group_write,
        "allowed_write": allowed,
        "after_allowed": after_allowed,
    }


def _approvals(client: ServiceNowClient, sys_id: str) -> list[dict[str, Any]]:
    try:
        rows = client.get_table(
            "sysapproval_approver",
            query=f"sysapproval={sys_id}",
            fields=["sys_id", "state", "approver", "group", "source_table"],
            limit=20,
            display_value=True,
        )
    except ServiceNowError as exc:
        print(f"approvals: HTTP {exc.status_code}")
        return [{"error": str(exc), "status": exc.status_code}]
    print(f"approvals: {len(rows)}")
    return rows


def _historical_insert(client: ServiceNowClient) -> dict[str, Any]:
    body = {
        "short_description": f"{PROBE_MARKER} historical",
        "description": f"{PROBE_MARKER} discovery probe",
        "correlation_id": PROBE_MARKER,
        "type": "normal",
        "state": "3",
        "close_code": "successful",
        "close_notes": f"{PROBE_MARKER} historical close",
        "opened_at": "2025-06-01 12:00:00",
        "closed_at": "2025-06-01 13:00:00",
        "work_start": "2025-06-01 12:10:00",
        "work_end": "2025-06-01 12:40:00",
    }
    try:
        record = client.create_record("change_request", body)
    except ServiceNowError as exc:
        print(f"historical insert: HTTP {exc.status_code}")
        return {"ok": False, "status": exc.status_code, "error": str(exc)}
    sys_id = str(record.get("sys_id") or "")
    stored = _read_change(client, sys_id) if sys_id else None
    state = stored.get("state") if isinstance(stored, dict) else None
    close_code = stored.get("close_code") if isinstance(stored, dict) else None
    print(f"historical insert: state={state} close_code={close_code}")
    state_patch = None
    after_state_patch = None
    if sys_id and _SYS_ID_RE.fullmatch(sys_id):
        state_patch = _call(
            client,
            "PATCH",
            f"/api/now/table/change_request/{sys_id}",
            {"state": "3"},
        )
        after_state_patch = _read_change(client, sys_id)
        patched = (
            after_state_patch.get("state") if isinstance(after_state_patch, dict) else None
        )
        print(f"historical state patch: state={patched}")
    return {
        "ok": True,
        "sys_id": sys_id,
        "record": stored,
        "state_patch": state_patch,
        "after_state_patch": after_state_patch,
    }


def _conflict_probe(client: ServiceNowClient) -> dict[str, Any]:
    cis = client.get_table(
        "cmdb_ci_linux_server",
        query="nameISNOTEMPTY",
        fields=["sys_id", "name"],
        limit=1,
    )
    if not cis:
        print("conflict: no linux server")
        return {"error": "no linux server"}
    ci_id = str(cis[0]["sys_id"])
    window = {"start_date": "2026-11-07 02:00:00", "end_date": "2026-11-07 04:00:00"}
    first = _create_change(client, "conflict-a", "/api/sn_chg_rest/change/normal")
    second = _create_change(client, "conflict-b", "/api/sn_chg_rest/change/normal")
    linked = []
    checks = []
    for created in (first, second):
        sys_id = created.get("sys_id")
        if not sys_id:
            continue
        _call(client, "PATCH", f"/api/now/table/change_request/{sys_id}", window)
        linked.append(_attach_ci(client, sys_id, ci_id))
        checks.append(_start_conflict(client, sys_id))
    attached = sum(1 for item in linked if item.get("ok"))
    print(f"conflict: checks={len(checks)} ci_attached={attached}")
    return {
        "ci_name": cis[0].get("name"),
        "first": first.get("sys_id"),
        "second": second.get("sys_id"),
        "attach": linked,
        "checks": checks,
    }


def _attach_ci(client: ServiceNowClient, change_id: str, ci_id: str) -> dict[str, Any]:
    via_api = _call(
        client,
        "POST",
        f"/api/sn_chg_rest/change/{change_id}/ci",
        {"cmdb_ci": ci_id},
    )
    if via_api.get("ok"):
        return via_api
    try:
        record = client.create_record("task_ci", {"task": change_id, "ci_item": ci_id})
    except ServiceNowError as exc:
        return {"ok": False, "api": via_api, "task_ci_status": exc.status_code, "error": str(exc)}
    task_ci_id = record.get("sys_id")
    _remember_delete("task_ci", task_ci_id)
    return {"ok": True, "api": via_api, "task_ci": task_ci_id}


def _start_conflict(client: ServiceNowClient, change_id: str) -> dict[str, Any]:
    started = _call(client, "POST", f"/api/sn_chg_rest/change/{change_id}/conflict", {})
    status = _call(client, "GET", f"/api/sn_chg_rest/change/{change_id}/conflict")
    conflicts = []
    try:
        conflicts = client.get_table(
            "conflict",
            query=f"change={change_id}^ORconflicting_change={change_id}",
            fields=["sys_id", "type", "change", "conflicting_change", "configuration_item"],
            limit=20,
            display_value=True,
        )
    except ServiceNowError as exc:
        conflicts = [{"error": str(exc), "status": exc.status_code}]
    if not conflicts:
        time.sleep(3)
        status = _call(client, "GET", f"/api/sn_chg_rest/change/{change_id}/conflict")
        try:
            conflicts = client.get_table(
                "conflict",
                query=f"change={change_id}",
                fields=["sys_id", "type", "change", "conflicting_change"],
                limit=20,
                display_value=True,
            )
        except ServiceNowError as exc:
            conflicts = [{"error": str(exc), "status": exc.status_code}]
    return {"started": started, "status": status, "rows": conflicts}


def _blackout_probe(client: ServiceNowClient) -> dict[str, Any]:
    body = {
        "name": f"{PROBE_MARKER} service scope",
        "applies_to": "cmdb_ci_service",
        "condition": "nameSTARTSWITHSYN-DOES-NOT-EXIST",
        "time_zone": "America/New_York",
    }
    try:
        record = client.create_record("cmn_schedule_blackout", body)
    except ServiceNowError as exc:
        print(f"blackout create: HTTP {exc.status_code}")
        return {"ok": False, "status": exc.status_code, "error": str(exc)}
    sys_id = str(record.get("sys_id") or "")
    stored = {}
    if sys_id:
        rows = client.get_table(
            "cmn_schedule_blackout",
            query=f"sys_id={sys_id}",
            fields=["name", "applies_to", "condition", "time_zone", "source"],
            limit=1,
            display_value=True,
        )
        stored = rows[0] if rows else {}
    print(f"blackout applies_to={stored.get('applies_to')}")
    return {"ok": True, "sys_id": sys_id, "record": stored}


def _probe_user(client: ServiceNowClient, settings: Settings, evidence: dict[str, Any]) -> None:
    password = _compliant_password()
    _extra_secrets.append(password)
    role_rows = client.get_table(
        "sys_user_role",
        query="nameINsn_change_read,sn_change_write",
        fields=["name", "sys_id"],
        limit=10,
    )
    try:
        # A plain Table API write stores user_password without hashing, and basic
        # auth then rejects it. input_display_value makes the platform hash it.
        created = client.request(
            "POST",
            "/api/now/table/sys_user",
            params={
                "sysparm_input_display_value": "true",
                "sysparm_display_value": "false",
                "sysparm_exclude_reference_link": "true",
            },
            json={
                "user_name": PROBE_USER,
                "first_name": PROBE_MARKER,
                "last_name": "Probe",
                "email": "syn.probe@example.com",
                "user_password": password,
                "password_needs_reset": "false",
                "web_service_access_only": "true",
                "time_zone": "UTC",
                "active": "true",
            },
        )
        user = created.get("result")
        if not isinstance(user, dict):
            raise ServiceNowError("Create on sys_user did not return a record")
    except ServiceNowError as exc:
        print(f"probe user create: HTTP {exc.status_code}")
        evidence["probe_user"] = {"ok": False, "status": exc.status_code, "error": str(exc)}
        return
    user_id = str(user.get("sys_id") or "")
    role_links = _grant_roles(client, user_id, role_rows)
    stored = _probe_user_row(client, user_id)
    password_meta = _password_meta(stored.pop("user_password", None), password)
    login = _probe_login(settings, password)
    password_patch = None
    if not login.get("ok"):
        password_patch = _set_password(client, user_id, password)
        stored_after = _probe_user_row(client, user_id)
        password_meta = _password_meta(stored_after.pop("user_password", None), password)
        stored = stored_after
        login = _probe_login(settings, password)
    basic_auth_role = None
    if not login.get("ok"):
        basic_auth_role = _grant_named_role(client, user_id, "snc_basic_auth_api_access")
        login = _probe_login(settings, password)
    operations = _probe_operations(client, settings, password) if login.get("ok") else []
    print(
        "probe user:"
        f" web_service_access_only={stored.get('web_service_access_only')}"
        f" time_zone={stored.get('time_zone')} login={login.get('status')}"
        f" password_set={password_meta.get('returned_nonempty')}"
    )
    evidence["probe_user"] = {
        "ok": True,
        "roles_requested": [row.get("name") for row in role_rows],
        "role_links": role_links,
        "stored": stored,
        "password": password_meta,
        "password_patch": password_patch,
        "basic_auth_role": basic_auth_role,
        "login": login,
        "operations": operations,
    }


def _compliant_password() -> str:
    """A policy-shaped password. Callers must redact it and must not log it."""
    return "Aa1!" + secrets.token_urlsafe(18)


def _password_meta(stored_value: object, submitted: str) -> dict[str, Any]:
    text = "" if stored_value is None else str(stored_value)
    return {
        "returned_nonempty": bool(text),
        "returned_length": len(text),
        "matches_submitted": text == submitted,
    }


def _probe_user_row(client: ServiceNowClient, user_id: str) -> dict[str, Any]:
    rows = client.get_table(
        "sys_user",
        query=f"sys_id={user_id}",
        fields=["user_name", "web_service_access_only", "time_zone", "active", "user_password"],
        limit=1,
    )
    return dict(rows[0]) if rows else {}


def _set_password(client: ServiceNowClient, user_id: str, password: str) -> dict[str, Any]:
    if not _SYS_ID_RE.fullmatch(user_id):
        return {"ok": False, "error": "user id was not a sys_id"}
    try:
        client.request(
            "PATCH",
            f"/api/now/table/sys_user/{user_id}",
            params={
                "sysparm_input_display_value": "true",
                "sysparm_display_value": "false",
                "sysparm_exclude_reference_link": "true",
            },
            json={"user_password": password, "password_needs_reset": "false"},
        )
    except ServiceNowError as exc:
        return {"ok": False, "status": exc.status_code, "error": str(exc)}
    return {"ok": True, "status": 200}


def _grant_roles(
    client: ServiceNowClient,
    user_id: str,
    role_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    links = []
    for role in role_rows:
        links.append(_grant_role(client, user_id, str(role.get("name") or ""), role.get("sys_id")))
    return links


def _grant_named_role(client: ServiceNowClient, user_id: str, name: str) -> dict[str, Any]:
    rows = client.get_table(
        "sys_user_role",
        query=f"name={name}",
        fields=["name", "sys_id"],
        limit=1,
    )
    if not rows:
        return {"role": name, "ok": False, "error": "role was not found"}
    return _grant_role(client, user_id, name, rows[0].get("sys_id"))


def _grant_role(
    client: ServiceNowClient,
    user_id: str,
    name: str,
    role_id: object,
) -> dict[str, Any]:
    try:
        link = client.create_record(
            "sys_user_has_role",
            {"user": user_id, "role": role_id, "inherited": "false"},
        )
    except ServiceNowError as first_error:
        try:
            link = client.create_record(
                "sys_user_has_role",
                {"user": user_id, "role": role_id},
            )
        except ServiceNowError as exc:
            return {
                "role": name,
                "ok": False,
                "status": exc.status_code,
                "error": str(exc),
                "first_status": first_error.status_code,
            }
    _remember_delete("sys_user_has_role", link.get("sys_id"))
    return {"role": name, "ok": True, "sys_id": link.get("sys_id")}


def _probe_login(settings: Settings, password: str) -> dict[str, Any]:
    """Confirm the session first. A table 401 can be an ACL, not a rejected password."""
    attempts = [
        _probe_call(settings, password, "GET", "/api/now/ui/user/current", None),
        _probe_call(settings, password, "GET", "/api/now/table/change_request", None),
    ]
    current = next(item for item in attempts if item.get("path", "").endswith("user/current"))
    return {
        "ok": bool(current.get("ok")),
        "status": current.get("status"),
        "target": "ui/user/current",
        "attempts": attempts,
    }


def _probe_operations(
    client: ServiceNowClient,
    settings: Settings,
    password: str,
) -> list[dict[str, Any]]:
    """Try the calls agents need. Add itil or cmdb_read only after a 403."""
    results = [
        _probe_call(settings, password, "POST", "/api/sn_chg_rest/change/normal", {
            "short_description": f"{PROBE_MARKER} role-check",
            "correlation_id": PROBE_MARKER,
        }),
        _probe_call(settings, password, "GET", "/api/now/table/cmdb_ci", None),
    ]
    if any(item.get("status") == 403 for item in results):
        users = client.get_table(
            "sys_user",
            query=f"user_name={PROBE_USER}",
            fields=["sys_id"],
            limit=1,
        )
        user_id = str(users[0].get("sys_id") or "") if users else ""
        if user_id:
            grant = _grant_named_role(client, user_id, "itil")
            results.append({"step": "grant", **grant})
            results.append(
                _probe_call(settings, password, "POST", "/api/sn_chg_rest/change/normal", {
                    "short_description": f"{PROBE_MARKER} role-check-itil",
                    "correlation_id": PROBE_MARKER,
                })
            )
            results.append(_probe_call(settings, password, "GET", "/api/now/table/cmdb_ci", None))
            if results[-1].get("status") == 403:
                results.append(
                    {"step": "grant", **_grant_named_role(client, user_id, "cmdb_read")}
                )
                results.append(
                    _probe_call(settings, password, "GET", "/api/now/table/cmdb_ci", None)
                )
    return results


def _probe_call(
    settings: Settings,
    password: str,
    method: str,
    path: str,
    body: dict[str, Any] | None,
) -> dict[str, Any]:
    try:
        with ServiceNowClient(
            settings.sn_instance_url,
            PROBE_USER,
            password,
            secrets=[password, *settings.secret_values(), *_extra_secrets],
        ) as probe:
            if method == "GET" and path.startswith("/api/now/table/"):
                probe.request(
                    method,
                    path,
                    params={"sysparm_limit": "1", "sysparm_fields": "sys_id"},
                )
            elif method == "GET":
                probe.request(method, path)
            else:
                probe.request(method, path, json=body)
    except ServiceNowError as exc:
        return {"ok": False, "method": method, "path": path, "status": exc.status_code}
    return {"ok": True, "method": method, "path": path, "status": 200}


def _cleanup(client: ServiceNowClient) -> None:
    for table, sys_id in list(_extra_deletes):
        _delete_id(client, table, sys_id)
    changes = _safe_rows(
        client,
        "change_request",
        f"short_descriptionSTARTSWITH{PROBE_MARKER}^ORcorrelation_id={PROBE_MARKER}",
        ["sys_id"],
    )
    for change in changes:
        change_id = str(change.get("sys_id") or "")
        if not change_id:
            continue
        _delete_where(client, "sysapproval_approver", f"sysapproval={change_id}")
        _delete_where(client, "sysapproval_group", f"parent={change_id}")
        _delete_where(client, "change_task", f"change_request={change_id}^ORparent={change_id}")
        _delete_where(client, "task_ci", f"task={change_id}")
        _delete_where(client, "task_cmdb_ci_service", f"task={change_id}")
        _delete_where(
            client,
            "conflict",
            f"change={change_id}^ORconflicting_change={change_id}",
        )
        _delete_id(client, "change_request", change_id)
    _delete_where(client, "cmn_schedule_span", f"schedule.nameSTARTSWITH{PROBE_MARKER}")
    _delete_where(client, "cmn_schedule_blackout", f"nameSTARTSWITH{PROBE_MARKER}")
    _delete_where(client, "cmn_schedule", f"nameSTARTSWITH{PROBE_MARKER}")
    users = _safe_rows(
        client,
        "sys_user",
        f"user_name={PROBE_USER}^ORfirst_name={PROBE_MARKER}",
        ["sys_id"],
    )
    for user in users:
        user_id = str(user.get("sys_id") or "")
        if not user_id:
            continue
        _delete_where(client, "sys_user_has_role", probe_role_query(user_id))
        _delete_id(client, "sys_user", user_id)


def _residue(client: ServiceNowClient) -> list[dict[str, Any]]:
    results = []
    for table, query in residue_queries():
        try:
            rows = client.get_table(table, query=query, fields=["sys_id"], limit=20)
        except ServiceNowError as exc:
            results.append(
                {
                    "table": table,
                    "query": query,
                    "error": str(exc),
                    "status": exc.status_code,
                }
            )
            continue
        results.append({"table": table, "query": query, "count": len(rows)})
    return results


def _print_residue(rows: list[dict[str, Any]]) -> None:
    print("SYN-PROBE residue:")
    for row in rows:
        if "count" in row:
            print(f"  {row['table']}: {row['count']}")
        else:
            print(f"  {row['table']}: HTTP {row.get('status')}")


def _write_evidence(evidence: dict[str, Any], settings: Settings) -> None:
    text = json.dumps(evidence, indent=2, default=str)
    text = redact_text(text, [*settings.secret_values(), *_extra_secrets])
    path = repo_root() / "var" / "probe_evidence.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read_change(
    client: ServiceNowClient,
    sys_id: str,
    *,
    display_value: bool = False,
) -> dict[str, Any]:
    try:
        rows = client.get_table(
            "change_request",
            query=f"sys_id={sys_id}",
            fields=_CHANGE_FIELDS,
            limit=1,
            display_value=display_value,
        )
    except ServiceNowError as exc:
        return {"error": str(exc), "status": exc.status_code}
    return rows[0] if rows else {"missing": True}


def _call(
    client: ServiceNowClient,
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        payload = client.request(method, path, json=body)
    except ServiceNowError as exc:
        return {"ok": False, "status": exc.status_code, "error": str(exc)}
    # Take the id from the raw body. Compacting must not run first: it can turn
    # a display-value object into text, and that text is not a sys_id.
    return {
        "ok": True,
        "status": 200,
        "sys_id": _sys_id(payload),
        "payload": _compact(payload),
    }


def _delete_where(client: ServiceNowClient, table: str, query: str) -> None:
    for row in _safe_rows(client, table, query, ["sys_id"]):
        sys_id = str(row.get("sys_id") or "")
        if sys_id:
            _delete_id(client, table, sys_id)


def _delete_id(client: ServiceNowClient, table: str, sys_id: str) -> None:
    try:
        client.delete_record(table, sys_id)
    except ServiceNowError as exc:
        if exc.status_code != 404:
            print(f"delete {table} failed: HTTP {exc.status_code}")


def _safe_rows(
    client: ServiceNowClient,
    table: str,
    query: str,
    fields: list[str],
) -> list[dict[str, Any]]:
    try:
        return client.get_table(table, query=query, fields=fields, limit=50)
    except ServiceNowError as exc:
        print(f"query {table} failed: HTTP {exc.status_code}")
        return []


def _validated_sys_id(created: dict[str, Any]) -> str | None:
    found = created.get("sys_id")
    if isinstance(found, str) and _SYS_ID_RE.fullmatch(found):
        return found
    found = _sys_id(created.get("payload"))
    if isinstance(found, str) and _SYS_ID_RE.fullmatch(found):
        return found
    return None


def _sys_id(payload: object) -> str | None:
    seen: set[int] = set()

    def walk(value: object) -> str | None:
        if isinstance(value, str):
            text = value.strip()
            if _SYS_ID_RE.fullmatch(text):
                return text
            if text.startswith("{") and text.endswith("}"):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    return None
                return walk(parsed)
            return None
        if not isinstance(value, dict):
            return None
        marker = id(value)
        if marker in seen:
            return None
        seen.add(marker)
        if "sys_id" in value:
            return walk(value.get("sys_id"))
        if "result" in value:
            return walk(value.get("result"))
        raw = value.get("value")
        if raw is None:
            raw = value.get("display_value")
        if raw is None:
            return None
        return walk(str(raw))

    return walk(payload)


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    result = payload.get("result", payload)
    if isinstance(result, list):
        return {"result": [_compact_value(item) for item in result[:40]]}
    if isinstance(result, dict):
        return {"result": _compact_value(result)}
    return {"result": result}


def _compact_value(value: object) -> object:
    if not isinstance(value, dict):
        return value
    wrapper_keys = {"value", "display_value", "display_value_internal", "link"}
    if ("value" in value or "display_value" in value) and set(value).issubset(wrapper_keys):
        return {"value": value.get("value"), "display": value.get("display_value")}
    kept: dict[str, Any] = {}
    for key, item in value.items():
        rendered = json.dumps(item, default=str)
        if len(rendered) > 400:
            continue
        if isinstance(item, dict):
            kept[key] = _compact_value(item)
        else:
            kept[key] = item
    return kept


def _remember_delete(table: str, sys_id: object) -> None:
    text = str(sys_id or "")
    if table in _EXTRA_TABLES and _SYS_ID_RE.fullmatch(text):
        _extra_deletes.append((table, text))


def _named_group(client: ServiceNowClient, name: str) -> str | None:
    rows = client.get_table(
        "sys_user_group",
        query=f"name={name}",
        fields=["sys_id"],
        limit=1,
    )
    if not rows:
        return None
    found = str(rows[0].get("sys_id") or "")
    return found if _SYS_ID_RE.fullmatch(found) else None


def _state_is(record: dict[str, Any] | None, expected: str) -> bool:
    if not isinstance(record, dict) or record.get("state") is None:
        return False
    return str(record.get("state")) == expected


def _fill_transition_fields(client: ServiceNowClient, sys_id: str) -> None:
    cis = client.get_table(
        "cmdb_ci_linux_server",
        query="nameISNOTEMPTY",
        fields=["sys_id"],
        limit=1,
    )
    body: dict[str, str] = {
        "description": f"{PROBE_MARKER} discovery probe",
        "short_description": f"{PROBE_MARKER} transition",
    }
    ci_id = str(cis[0].get("sys_id") or "") if cis else ""
    if _SYS_ID_RE.fullmatch(ci_id):
        body["cmdb_ci"] = ci_id
    _call(client, "PATCH", f"/api/now/table/change_request/{sys_id}", body)


def _pair(record: dict[str, Any] | None) -> str:
    if not isinstance(record, dict):
        return "missing"
    return f"risk={record.get('risk')} impact={record.get('impact')}"


def main() -> int:
    from cm_agents.cli import configure_logging
    from cm_agents.settings import SettingsError, load_settings

    try:
        settings = load_settings()
    except SettingsError as exc:
        print(str(exc))
        return 2
    configure_logging(settings.secret_values(), level=logging.WARNING)
    return run_discover(settings)


if __name__ == "__main__":
    raise SystemExit(main())
