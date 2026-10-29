"""Choose a window, then leave risk to score that window."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from cm_agents.agents.context import current
from cm_agents.agents.risk import judge_plans, score_window
from cm_agents.clock import now
from cm_agents.data.import_time import UTC, parse_utc
from cm_agents.enablement.guard import blocks_schedule
from cm_agents.enablement.route import lead_days
from cm_agents.enablement.windows import blocks, earliest_window, inside_maintenance
from cm_agents.servicenow.changes import (
    active_on_ci,
    conflicts_for,
    write_dates,
    write_note,
)


def run_scheduling(state: dict[str, Any]) -> dict[str, Any]:
    ctx = current()
    requested_start, requested_end = _proposed(state)
    start, end = requested_start, requested_end
    write_dates(ctx.client, state["change_sys_id"], _text(start), _text(end))
    checklist = judge_plans(state)
    score = score_window(state, _text(start), _text(end), checklist)
    lead = _lead(state, score["tier"])
    occupied = _occupied(state)
    moved = False
    source = "ok"
    seen: list[dict[str, Any]] = []
    reasons: list[str] = []
    blocked_types: list[str] = []
    blocked_source = ""
    for _pass in range(3):
        seen, source = conflicts_for(ctx.client, state["change_sys_id"])
        reasons = _reasons(state, start, end, lead, seen, source, occupied)
        if "conflict" in reasons and not blocked_types:
            blocked_types = _conflict_names(seen, source, state["change_type"])
            blocked_source = source
        if not reasons or state["change_type"] == "emergency":
            break
        span = _next_window(state, start, end, lead, occupied, reasons)
        if span is None:
            payload = _payload(
                requested_start, requested_end, start, end, moved, reasons, seen, source
            )
            _remember_block(payload, blocked_types, blocked_source)
            return {"checklist": checklist, "schedule": payload, "error": "no compliant window"}
        start, end = span
        moved = True
        write_dates(ctx.client, state["change_sys_id"], _text(start), _text(end))
        revised = score_window(state, _text(start), _text(end), checklist)
        lead = _lead(state, revised["tier"])
    else:
        seen, source = conflicts_for(ctx.client, state["change_sys_id"])
        reasons = _reasons(state, start, end, lead, seen, source, occupied)
    if reasons and state["change_type"] != "emergency":
        payload = _payload(requested_start, requested_end, start, end, moved, reasons, seen, source)
        _remember_block(payload, blocked_types, blocked_source)
        return {"checklist": checklist, "schedule": payload, "error": "window stayed blocked"}
    inside = inside_maintenance(start, end, _critical(state))
    kept_reasons = reasons if state["change_type"] == "emergency" else []
    payload = _payload(
        requested_start, requested_end, start, end, moved, kept_reasons, seen, source
    )
    _remember_block(payload, blocked_types, blocked_source)
    payload["maintenance"] = "inside" if inside else "outside"
    payload["compliant"] = state["change_type"] == "emergency" or not kept_reasons
    _note(state, payload)
    return {"checklist": checklist, "schedule": payload, "error": ""}


def _proposed(state: dict[str, Any]) -> tuple[datetime, datetime]:
    request = state["request"]
    if str(request.get("proposed_window") or "") == "next_maintenance":
        duration = timedelta(hours=2)
        found = earliest_window(
            now=now(),
            duration=duration,
            tier=_critical(state),
            service=str(state.get("service") or ""),
            lead_business_days=_lead(state, "high"),
            freezes=current().policy["freezes"],
            occupied=[],
        )
        if found is None:
            raise RuntimeError("no maintenance window is available")
        return found
    start = parse_utc(str(request["proposed_start"]))
    end = parse_utc(str(request["proposed_end"]))
    return start, end


def _lead(state: dict[str, Any], tier: str) -> int:
    if state["change_type"] == "standard":
        return lead_days(current().policy, "standard", tier)
    if state["change_type"] == "emergency":
        return lead_days(current().policy, "emergency", tier)
    return lead_days(current().policy, "normal", tier)


def _critical(state: dict[str, Any]) -> int:
    tier = int(state.get("service_tier") or 3)
    return tier or 3


def _occupied(state: dict[str, Any]) -> list[tuple[datetime, datetime]]:
    spans = []
    for ci in state.get("affected_cis") or []:
        for row in active_on_ci(current().client, ci["sys_id"], state["change_sys_id"]):
            spans.append((parse_utc(row["start"]), parse_utc(row["end"])))
    return spans


def _reasons(
    state: dict[str, Any],
    start: datetime,
    end: datetime,
    lead: int,
    conflicts: list[dict[str, Any]],
    source: str,
    occupied: list[tuple[datetime, datetime]],
) -> list[str]:
    schedule_conflict = any(
        blocks_schedule(str(row.get("type") or ""), state["change_type"]) for row in conflicts
    )
    if source == "unreadable":
        schedule_conflict = any(
            start < taken_end and taken_start < end for taken_start, taken_end in occupied
        )
    return blocks(
        now=now(),
        start=start,
        end=end,
        change_type=state["change_type"],
        tier=_critical(state),
        service=str(state.get("service") or ""),
        lead_business_days=lead,
        freezes=current().policy["freezes"],
        schedule_conflict=schedule_conflict,
    )


def _next_window(
    state: dict[str, Any],
    start: datetime,
    end: datetime,
    lead: int,
    occupied: list[tuple[datetime, datetime]],
    reasons: list[str],
) -> tuple[datetime, datetime] | None:
    taken = list(occupied)
    if "conflict" in reasons:
        taken.append((start, end))
    return earliest_window(
        now=now(),
        duration=end - start,
        tier=_critical(state),
        service=str(state.get("service") or ""),
        lead_business_days=lead,
        freezes=current().policy["freezes"],
        occupied=taken,
    )


def _conflict_names(
    conflicts: list[dict[str, Any]], source: str, change_type: str
) -> list[str]:
    names = [
        str(row.get("type") or "")
        for row in conflicts
        if blocks_schedule(str(row.get("type") or ""), change_type)
    ]
    if names:
        return names
    if source == "unreadable":
        return ["local overlap"]
    return []


def _remember_block(payload: dict[str, Any], types: list[str], source: str) -> None:
    payload["moved_because"] = types
    payload["blocked_source"] = source


def _payload(
    requested_start: datetime,
    requested_end: datetime,
    start: datetime,
    end: datetime,
    moved: bool,
    reasons: list[str],
    conflicts: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    types = [str(row.get("type") or "") for row in conflicts]
    return {
        "requested_start": _text(requested_start),
        "requested_end": _text(requested_end),
        "start": _text(start),
        "end": _text(end),
        "moved": moved or _text(start) != _text(requested_start),
        "blocks": reasons,
        "conflict_types": types,
        "conflict_source": source,
        "maintenance": "",
        "compliant": not reasons,
    }


def _note(state: dict[str, Any], schedule: dict[str, Any]) -> None:
    types = ", ".join(schedule["conflict_types"]) or "none"
    decision = "moved" if schedule["moved"] else "kept"
    reason = (
        f"requested {schedule['requested_start']} to {schedule['requested_end']} UTC; "
        f"chosen {schedule['start']} to {schedule['end']} UTC; "
        f"maintenance {schedule['maintenance']}; conflicts {types}; "
        f"source {schedule['conflict_source']}"
    )
    if schedule.get("moved_because"):
        reason = (
            f"{reason}; moved because {', '.join(schedule['moved_because'])} "
            f"({schedule.get('blocked_source') or schedule['conflict_source']})"
        )
    if schedule["blocks"]:
        reason = f"{reason}; flags {', '.join(schedule['blocks'])}"
    write_note(
        current().client,
        state["change_sys_id"],
        thread_id=state["thread_id"],
        agent="scheduling",
        decision=decision,
        reason=reason,
        record=str(state.get("change_number") or ""),
    )


def _text(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")
