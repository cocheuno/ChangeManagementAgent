"""Turn a request into a typed change, or list exactly what is missing."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from cm_agents.agents.context import current
from cm_agents.data.import_time import UTC, parse_utc
from cm_agents.enablement.guard import injection_markers
from cm_agents.enablement.resolve import resolution_gap, resolve_ci_name
from cm_agents.enablement.risk_score import impacted_services
from cm_agents.servicenow.changes import (
    attach_affected,
    create_change,
    create_standard,
    exact_ci,
    find_by_correlation,
    find_incident,
    find_release,
    group_id,
    journal,
    remember_change,
    template_id,
    update_fields,
    write_note,
)

CLOSED_INCIDENT = {"6", "7"}
_PLAN_FIELDS = ("justification", "implementation_plan", "backout_plan", "test_plan")


def run_intake(state: dict[str, Any]) -> dict[str, Any]:
    ctx = current()
    request = dict(state["request"])
    thread_id = state["thread_id"]
    names, gaps = _resolve_cis(ctx.client, _names(request.get("cis")))
    services = _services(ctx.fixtures, [row["name"] for row in names])
    service_rows = [row for row in ctx.fixtures["services"] if row["name"] in services]
    primary = min(service_rows, key=lambda row: int(row["tier"])) if service_rows else None
    if names and primary is None:
        gaps.append("the affected CI has no catalog service")
    change_type, why, incident = _classify(ctx, request, names)
    if change_type != "standard":
        gaps.extend(_missing_plans(request))
        if not _has_window(request):
            gaps.append("proposed window is missing")
    if change_type == "standard" and not request.get("template"):
        gaps.append("standard template name is missing")
    group_name = str(primary["group"]) if primary else ""
    if change_type != "standard" and not group_name:
        gaps.append("assignment group is missing")
    record = find_by_correlation(ctx.client, thread_id)
    if record is None and not gaps:
        record = _create(ctx, request, thread_id, change_type, group_name, incident, services)
    elif record is None and gaps:
        record = _create_shell(ctx, request, thread_id)
    if record is None:
        return {"gaps": gaps, "error": "change was not created"}
    if not gaps:
        _fill(ctx, record, request, change_type, group_name, names, incident, services)
    flagged = injection_markers(
        str(request.get("description") or ""),
        str(request.get("summary") or ""),
        str(request.get("justification") or ""),
    )
    if flagged and not _already_noted(ctx.client, str(record["sys_id"]), "injection"):
        write_note(
            ctx.client,
            str(record["sys_id"]),
            thread_id=thread_id,
            agent="intake",
            decision="injection",
            reason=(
                "record text tells the agent to ignore policy. "
                "The text was treated as data and was not followed. Markers: "
                + ", ".join(flagged)
            ),
            record=str(record.get("number") or record["sys_id"]),
        )
    if not _already_noted(ctx.client, str(record["sys_id"]), "classified"):
        write_note(
            ctx.client,
            str(record["sys_id"]),
            thread_id=thread_id,
            agent="intake",
            decision="classified",
            reason=why,
            record=str(record.get("number") or record["sys_id"]),
        )
    if request.get("simulated_now") and not _already_noted(
        ctx.client, str(record["sys_id"]), "clock"
    ):
        moment = parse_utc(str(request["simulated_now"])).astimezone(UTC)
        write_note(
            ctx.client,
            str(record["sys_id"]),
            thread_id=thread_id,
            agent="intake",
            decision="clock",
            reason=f"simulated now {moment.strftime('%Y-%m-%d %H:%M:%S')} UTC",
            record=str(record.get("number") or record["sys_id"]),
        )
    if gaps and not _already_noted(ctx.client, str(record["sys_id"]), "gaps"):
        write_note(
            ctx.client,
            str(record["sys_id"]),
            thread_id=thread_id,
            agent="intake",
            decision="gaps",
            reason="; ".join(gaps),
            record=str(record.get("number") or record["sys_id"]),
        )
    return {
        "request": request,
        "change_sys_id": str(record["sys_id"]),
        "change_number": str(record.get("number") or ""),
        "change_type": change_type,
        "service": str(primary["name"]) if primary else "",
        "service_tier": int(primary["tier"]) if primary else 0,
        "assignment_group": group_name,
        "affected_cis": names,
        "impacted_service_names": services,
        "gaps": gaps,
        "injection": flagged,
        "release_member": bool(request.get("release")),
        "error": "",
    }


def _names(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []


def _resolve_cis(client: object, requested: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    found: list[dict[str, str]] = []
    gaps: list[str] = []
    for name in requested:
        exact = exact_ci(client, name)  # type: ignore[arg-type]
        matches = [str(row["name"]) for row in exact if row.get("name") == name]
        rows = exact
        if not matches:
            from cm_agents.servicenow.changes import containing_cis

            rows = containing_cis(client, name)  # type: ignore[arg-type]
            matches = resolve_ci_name(name, [str(row.get("name") or "") for row in rows])
        gap = resolution_gap(name, matches)
        if gap:
            gaps.append(gap)
            continue
        chosen = next(row for row in rows if row.get("name") == matches[0])
        found.append(
            {
                "name": str(chosen["name"]),
                "sys_id": str(chosen["sys_id"]),
                "ci_class": str(chosen.get("sys_class_name") or ""),
            }
        )
    if not requested:
        gaps.append("affected CI is missing")
    return found, gaps


def _services(fixtures: dict[str, Any], names: list[str]) -> list[str]:
    ci_by_name = {row["name"]: row for row in fixtures["cis"]}
    parents: dict[str, list[str]] = defaultdict(list)
    for link in fixtures["relationships"]:
        parents[link["child"]].append(link["parent"])
    return impacted_services(names, ci_by_name, parents)


def _classify(
    ctx: Any, request: dict[str, Any], cis: list[dict[str, str]]
) -> tuple[str, str, dict[str, Any] | None]:
    incident = None
    if request.get("incident"):
        incident = find_incident(ctx.client, str(request["incident"]))
    security = bool(request.get("security_flag")) and bool(
        str(request.get("justification") or "").strip()
    )
    ci_ids = {row["sys_id"] for row in cis}
    open_major = False
    if incident:
        priority = str(incident.get("priority") or "")
        state = str(incident.get("state") or "")
        on_ci = not ci_ids or str(incident.get("cmdb_ci") or "") in ci_ids
        open_major = priority in {"1", "2"} and state not in CLOSED_INCIDENT and on_ci
    if security:
        return (
            "emergency",
            "emergency because the request has a security flag and a justification",
            incident,
        )
    if open_major:
        return (
            "emergency",
            "emergency because an open P1 or P2 incident is on an affected CI",
            incident,
        )
    if request.get("template"):
        return "standard", f"standard template {request['template']}", incident
    if request.get("requested_type") == "emergency" or request.get("incident"):
        return (
            "normal",
            "downgraded to normal: no open P1 or P2 on an affected CI "
            "and no security flag with a justification",
            incident,
        )
    return "normal", "normal change", incident


def _missing_plans(request: dict[str, Any]) -> list[str]:
    missing = []
    for field in _PLAN_FIELDS:
        if not str(request.get(field) or "").strip():
            missing.append(f"{field} is missing")
    return missing


def _has_window(request: dict[str, Any]) -> bool:
    if str(request.get("proposed_window") or "") == "next_maintenance":
        return True
    return bool(request.get("proposed_start") and request.get("proposed_end"))


def _create_shell(ctx: Any, request: dict[str, Any], thread_id: str) -> dict[str, Any]:
    record = create_change(
        ctx.client,
        "normal",
        {
            "short_description": str(request["summary"]),
            "description": str(request["description"]),
            "correlation_id": thread_id,
        },
    )
    remember_change(str(record["sys_id"]), thread_id)
    return record


def _create(
    ctx: Any,
    request: dict[str, Any],
    thread_id: str,
    change_type: str,
    group_name: str,
    incident: dict[str, Any] | None,
    services: list[str],
) -> dict[str, Any]:
    body = {
        "short_description": str(request["summary"]),
        "description": str(request["description"]),
        "correlation_id": thread_id,
    }
    if change_type == "standard":
        producer = template_id(ctx.client, str(request["template"]))
        if not producer:
            raise RuntimeError(f"standard template {request['template']} was not found")
        record = create_standard(ctx.client, producer, body)
    else:
        record = create_change(ctx.client, change_type, body)
    remember_change(str(record["sys_id"]), thread_id)
    _ = (group_name, incident, services)
    return record


def _fill(
    ctx: Any,
    record: dict[str, Any],
    request: dict[str, Any],
    change_type: str,
    group_name: str,
    cis: list[dict[str, str]],
    incident: dict[str, Any] | None,
    services: list[str],
) -> None:
    method = _method(request)
    plans = _plans(request, method)
    fields: dict[str, Any] = {
        "short_description": str(request["summary"]),
        "description": str(request["description"]),
        "justification": plans["justification"],
        "implementation_plan": plans["implementation_plan"],
        "backout_plan": plans["backout_plan"],
        "test_plan": plans["test_plan"],
    }
    if group_name:
        fields["assignment_group"] = group_id(ctx.client, group_name)
    if cis:
        fields["cmdb_ci"] = cis[0]["sys_id"]
    update_fields(ctx.client, str(record["sys_id"]), fields)
    if cis and str(record.get("state") or "") == "-5":
        attach_affected(ctx.client, str(record["sys_id"]), [row["sys_id"] for row in cis])
    elif cis:
        attach_affected(ctx.client, str(record["sys_id"]), [row["sys_id"] for row in cis])
    _link_parents(ctx, record, request, services, incident)
    request["deployment_method"] = method
    request["implementation_plan"] = plans["implementation_plan"]
    request["backout_plan"] = plans["backout_plan"]
    request["test_plan"] = plans["test_plan"]
    request["justification"] = plans["justification"]
    _ = change_type


def _link_parents(
    ctx: Any,
    record: dict[str, Any],
    request: dict[str, Any],
    services: list[str],
    incident: dict[str, Any] | None,
) -> None:
    parent = ""
    if incident and request.get("incident"):
        parent = str(incident.get("sys_id") or "")
    if request.get("release") and services:
        summary = f"SYN RELEASE {services[0]} {request['release']}"
        release_id = find_release(ctx.client, summary)
        if release_id:
            parent = release_id
        else:
            request["_release_gap"] = f"release {summary} was not found"
    if parent and str(record.get("parent") or "") != parent:
        update_fields(ctx.client, str(record["sys_id"]), {"parent": parent})


def _plans(request: dict[str, Any], method: str) -> dict[str, str]:
    label = "AUTOMATED" if method == "automated" else "MANUAL"
    line = f"Deployment method: {label}"
    implementation = str(request.get("implementation_plan") or "").strip()
    if not implementation.startswith("Deployment method:"):
        implementation = f"{line}\n{implementation}".strip()
    return {
        "justification": str(request.get("justification") or "").strip(),
        "implementation_plan": implementation,
        "backout_plan": str(request.get("backout_plan") or "").strip(),
        "test_plan": str(request.get("test_plan") or "").strip(),
    }


def _method(request: dict[str, Any]) -> str:
    value = str(request.get("deployment_method") or "automated").strip().lower()
    if value not in {"automated", "manual"}:
        return "automated"
    return value


def _already_noted(client: object, sys_id: str, decision: str) -> bool:
    needle = f"] {decision}:"
    return any(needle in text for text in journal(client, sys_id))  # type: ignore[arg-type]
