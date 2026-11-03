"""Metrics and standard-change candidates, read from ServiceNow.

The formulas live here. They do not import the generator. The population
rules are in docs/ASSUMPTIONS.md. The model writes the commentary only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from cm_agents.data.queries import (
    CI,
    GROUP,
    counts_in_metrics,
    metric_change_query,
    metric_incident_query,
)
from cm_agents.llm import complete, record_block
from cm_agents.rounding import percent, round_1
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import Settings, repo_root

_FORMAT = "%Y-%m-%d %H:%M:%S"
_WEEK_SECONDS = 7 * 24 * 3600
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
_PERIOD_NAME = re.compile(r"[A-Za-z0-9._-]{1,80}")
SERVICE_NAMES = (
    "SYN Order Fulfillment",
    "SYN Online Store",
    "SYN Payments",
    "SYN HR Portal",
)
_CLOSED = "3"
_PAGE = 200
_CAP = 5000


class MetricsError(ValueError):
    """A metric input is missing or the commentary cites a number of its own."""


class Commentary(BaseModel):
    commentary: str = Field(min_length=1)


@dataclass(frozen=True)
class ChangeView:
    sys_id: str
    opened_at: datetime
    work_end: datetime | None
    end_date: datetime | None
    state: str
    change_type: str
    close_code: str
    service: str
    ci_environment: str
    ci_class: str
    assignment_group: str
    short_description: str
    release: bool


@dataclass(frozen=True)
class IncidentView:
    opened_at: datetime
    resolved_at: datetime | None
    caused_change_id: str


def parse_stamp(value: str) -> datetime:
    text = value.strip()
    if len(text) < 19:
        raise MetricsError("period must be YYYY-MM-DD HH:MM:SS UTC")
    try:
        return datetime.strptime(text[:19], _FORMAT)
    except ValueError as exc:
        raise MetricsError("period must be YYYY-MM-DD HH:MM:SS UTC") from exc


def service_from_description(description: str) -> str:
    found = [name for name in SERVICE_NAMES if name in description]
    if len(found) != 1:
        raise MetricsError("a change description must name one service")
    return found[0]


def is_release(correlation_id: str, summary: str) -> bool:
    return correlation_id.startswith("SYN-REL-") or summary.startswith("SYN RELEASE ")


def counts_as_prod(change: ChangeView) -> bool:
    """A release is a production go-live. Any other change follows its CI.

    The fixture word is prod. The instance choice value is Production.
    """
    if change.release:
        return True
    return change.ci_environment in {"prod", "Production"}


def proposed_template(signature: str) -> str:
    rest = signature[4:] if signature.startswith("syn ") else signature
    return f"SYN Standard {rest}"


def median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def compute_metrics(
    changes: list[ChangeView],
    incidents: list[IncidentView],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    """§8.4 for one half-open window. Release on-time uses every release."""
    if start >= end:
        raise MetricsError("period start must be before the end")
    period = [row for row in changes if start <= row.opened_at < end]
    implemented = [row for row in period if row.state == _CLOSED]
    caused = {row.caused_change_id for row in incidents if row.caused_change_id}
    weeks = (end - start).total_seconds() / _WEEK_SECONDS
    return {
        "volume_by_type": _count(period, "change_type"),
        "volume_by_service": _count(period, "service"),
        "volume_by_month": _count_month(period),
        "success_rate_pct": _success(implemented),
        "success_rate_by_type": {
            change_type: _success([row for row in implemented if row.change_type == change_type])
            for change_type in ("standard", "normal", "emergency")
        },
        "failure_rate_pct": _failure(implemented, caused),
        "emergency_ratio_pct": _share(period, "emergency"),
        "standard_share_pct": _share(period, "standard"),
        "lead_time_hours": _lead_time(implemented),
        "deployment_frequency_per_week": _frequency(implemented, weeks),
        "mttr_hours": _mttr(changes, incidents, start, end),
        "release_on_time_pct": _release_on_time(changes),
    }


def find_candidates(
    changes: list[ChangeView],
    incidents: list[IncidentView],
    start: datetime,
    end: datetime,
) -> list[dict[str, Any]]:
    """Normal changes with one signature, at least 10 closes, and no failures."""
    caused = {row.caused_change_id for row in incidents if row.caused_change_id}
    groups: dict[tuple[str, str, str], list[ChangeView]] = {}
    for row in changes:
        if row.release or row.change_type != "normal" or row.state != _CLOSED:
            continue
        if row.opened_at < start or row.opened_at >= end:
            continue
        key = (_signature(row.short_description), row.ci_class, row.assignment_group)
        groups.setdefault(key, []).append(row)
    found = []
    for (signature, ci_class, group), members in groups.items():
        failures = sum(1 for row in members if row.close_code == "unsuccessful")
        caused_count = sum(1 for row in members if row.sys_id in caused)
        if len(members) >= 10 and failures == 0 and caused_count == 0:
            found.append(
                {
                    "signature": signature,
                    "ci_class": ci_class,
                    "assignment_group": group,
                    "executions": len(members),
                    "failures": failures,
                    "caused_incidents": caused_count,
                    "proposed_template": proposed_template(signature),
                }
            )
    found.sort(key=lambda row: (row["signature"], row["ci_class"], row["assignment_group"]))
    return found


def unknown_numbers(commentary: str, table: object) -> list[str]:
    """Number tokens in the commentary that do not appear in the table."""
    allowed = _table_numbers(table)
    unknown = []
    for token in _NUMBER.findall(commentary):
        value = float(token.replace(",", ""))
        if value not in allowed:
            unknown.append(token)
    return unknown


def commentary_table(metrics: dict[str, Any], start: str, end: str) -> dict[str, Any]:
    return {"period_end": end, "period_start": start, **metrics}


def run_metrics_report(
    settings: Settings,
    *,
    period: str,
    start_text: str,
    end_text: str,
) -> dict[str, Any]:
    if _PERIOD_NAME.fullmatch(period) is None:
        raise MetricsError("period name must be letters, digits, dots, underscores, or hyphens")
    start = parse_stamp(start_text)
    end = parse_stamp(end_text)
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=180,
    ) as client:
        changes, incidents = load_views(client)
    metrics = compute_metrics(changes, incidents, start, end)
    candidates = find_candidates(changes, incidents, start, end)
    table = commentary_table(metrics, start_text[:19], end_text[:19])
    commentary = _commentary(settings, table, period)
    path = repo_root() / "reports" / "metrics" / f"{period}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        _render(period, start_text[:19], end_text[:19], metrics, commentary, candidates),
        encoding="utf-8",
    )
    return {"metrics": metrics, "candidates": candidates, "report": path.name}


def load_views(client: ServiceNowClient) -> tuple[list[ChangeView], list[IncidentView]]:
    groups = {
        str(row["sys_id"]): str(row.get("name") or "")
        for row in _pages(client, "sys_user_group", GROUP, ["sys_id", "name"])
    }
    cis = {
        str(row["sys_id"]): row
        for row in _pages(
            client,
            "cmdb_ci",
            CI,
            ["sys_id", "name", "sys_class_name", "environment"],
        )
    }
    changes = []
    for row in _pages(
        client,
        "change_request",
        metric_change_query(),
        [
            "sys_id",
            "correlation_id",
            "opened_at",
            "work_end",
            "end_date",
            "state",
            "type",
            "close_code",
            "short_description",
            "description",
            "assignment_group",
            "cmdb_ci",
        ],
    ):
        correlation = str(row.get("correlation_id") or "")
        if not counts_in_metrics(correlation):
            continue
        summary = str(row.get("short_description") or "")
        ci = cis.get(str(row.get("cmdb_ci") or ""))
        if ci is None:
            raise MetricsError(f"{summary or correlation} has no configuration item")
        group_id = str(row.get("assignment_group") or "")
        group = groups.get(group_id)
        if not group:
            raise MetricsError(f"{summary or correlation} has no assignment group")
        changes.append(
            ChangeView(
                sys_id=str(row["sys_id"]),
                opened_at=_stored_stamp(row.get("opened_at")),
                work_end=_optional_stamp(row.get("work_end")),
                end_date=_optional_stamp(row.get("end_date")),
                state=str(row.get("state") or ""),
                change_type=str(row.get("type") or ""),
                close_code=str(row.get("close_code") or ""),
                service=service_from_description(str(row.get("description") or "")),
                ci_environment=str(ci.get("environment") or ""),
                ci_class=str(ci.get("sys_class_name") or ""),
                assignment_group=group,
                short_description=summary,
                release=is_release(correlation, summary),
            )
        )
    incidents = []
    for row in _pages(
        client,
        "incident",
        metric_incident_query(),
        ["sys_id", "correlation_id", "opened_at", "resolved_at", "u_caused_by"],
    ):
        correlation = str(row.get("correlation_id") or "")
        if not counts_in_metrics(correlation):
            continue
        incidents.append(
            IncidentView(
                opened_at=_stored_stamp(row.get("opened_at")),
                resolved_at=_optional_stamp(row.get("resolved_at")),
                caused_change_id=str(row.get("u_caused_by") or ""),
            )
        )
    return changes, incidents


def _pages(
    client: ServiceNowClient,
    table: str,
    query: str,
    fields: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while offset < _CAP:
        page = client.get_table(
            table,
            query=query,
            fields=fields,
            limit=_PAGE,
            offset=offset,
        )
        rows.extend(page)
        if len(page) < _PAGE:
            return rows
        offset += _PAGE
    raise MetricsError(f"{table} returned more than {_CAP} rows")


def _stored_stamp(value: object) -> datetime:
    text = str(value or "").strip()
    if len(text) < 19:
        raise MetricsError("a required date is empty")
    return datetime.strptime(text[:19], _FORMAT)


def _optional_stamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if len(text) < 19:
        return None
    return datetime.strptime(text[:19], _FORMAT)


def _count(rows: list[ChangeView], field: str) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows:
        key = str(getattr(row, field))
        totals[key] = totals.get(key, 0) + 1
    return totals


def _count_month(rows: list[ChangeView]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows:
        key = row.opened_at.strftime("%Y-%m")
        totals[key] = totals.get(key, 0) + 1
    return totals


def _success(rows: list[ChangeView]) -> float:
    ok = sum(1 for row in rows if row.close_code in {"successful", "successful_issues"})
    return percent(ok, len(rows))


def _failure(rows: list[ChangeView], caused: set[str]) -> float:
    failed = sum(
        1 for row in rows if row.close_code == "unsuccessful" or row.sys_id in caused
    )
    return percent(failed, len(rows))


def _share(rows: list[ChangeView], change_type: str) -> float:
    matched = sum(1 for row in rows if row.change_type == change_type)
    return percent(matched, len(rows))


def _lead_time(rows: list[ChangeView]) -> float:
    hours = []
    for row in rows:
        if row.work_end is None:
            continue
        hours.append((row.work_end - row.opened_at).total_seconds() / 3600)
    return round_1(median(hours))


def _frequency(rows: list[ChangeView], weeks: float) -> dict[str, float]:
    totals: dict[str, int] = {}
    for row in rows:
        if not counts_as_prod(row):
            continue
        totals[row.service] = totals.get(row.service, 0) + 1
    return {service: round_1(count / weeks) for service, count in sorted(totals.items())}


def _mttr(
    changes: list[ChangeView],
    incidents: list[IncidentView],
    start: datetime,
    end: datetime,
) -> float:
    change_ids = {row.sys_id for row in changes}
    hours = []
    for row in incidents:
        if row.caused_change_id not in change_ids or row.resolved_at is None:
            continue
        if row.opened_at < start or row.opened_at >= end:
            continue
        hours.append((row.resolved_at - row.opened_at).total_seconds() / 3600)
    return round_1(median(hours))


def _release_on_time(changes: list[ChangeView]) -> float:
    releases = [row for row in changes if row.release]
    on_time = 0
    for row in releases:
        if row.work_end is None or row.end_date is None:
            raise MetricsError("a release is missing its planned end or actual end")
        if row.work_end <= row.end_date:
            on_time += 1
    return percent(on_time, len(releases))


def _signature(summary: str) -> str:
    return " ".join(summary.lower().split())


def _table_numbers(table: object) -> set[float]:
    found: set[float] = set()

    def walk(value: object) -> None:
        if isinstance(value, bool):
            return
        if isinstance(value, int | float):
            found.add(float(value))
            return
        if isinstance(value, str):
            for token in _NUMBER.findall(value):
                found.add(float(token.replace(",", "")))
            return
        if isinstance(value, dict):
            for key, item in value.items():
                walk(key)
                walk(item)
            return
        if isinstance(value, list):
            for item in value:
                walk(item)

    walk(table)
    return found


def _commentary(settings: Settings, table: dict[str, Any], period: str) -> str:
    payload = json.dumps(table, indent=2, sort_keys=True)
    system = (
        "Write a short commentary on this change metrics table. "
        "Every number you write must already appear in the table. "
        "Do not calculate a new number, and do not add a date or a count "
        "that is not in the table."
    )
    draft = complete(
        settings,
        Commentary,
        system=system,
        user=record_block(payload),
        thread_id=f"SYN-S09-{period}",
        agent="review",
        action="metrics_commentary",
        record=period,
    )
    unknown = unknown_numbers(draft.commentary, table)
    if not unknown:
        return draft.commentary.strip()
    retry = complete(
        settings,
        Commentary,
        system=system,
        user=record_block(payload)
        + "\n\nDo not use these numbers. They are not in the table: "
        + ", ".join(unknown),
        thread_id=f"SYN-S09-{period}",
        agent="review",
        action="metrics_commentary",
        record=period,
    )
    unknown = unknown_numbers(retry.commentary, table)
    if unknown:
        joined = ", ".join(unknown)
        raise MetricsError(f"commentary cites numbers that are not in the table: {joined}")
    return retry.commentary.strip()


def _render(
    period: str,
    start: str,
    end: str,
    metrics: dict[str, Any],
    commentary: str,
    candidates: list[dict[str, Any]],
) -> str:
    lines = [
        f"# Metrics {period}",
        "",
        f"Period {start} UTC inclusive through {end} UTC exclusive.",
        "",
        "## Table",
        "",
        "```json",
        json.dumps(metrics, indent=2, sort_keys=True),
        "```",
        "",
        "## Commentary",
        "",
        commentary,
        "",
        "## Standard change candidates",
        "",
    ]
    if not candidates:
        lines.append("No candidate meets the rule.")
    for row in candidates:
        lines.append(
            f"- {row['signature']}: executions {row['executions']}, "
            f"failures {row['failures']}, caused incidents {row['caused_incidents']}, "
            f"class {row['ci_class']}, group {row['assignment_group']}, "
            f"proposed template {row['proposed_template']}"
        )
    lines.append("")
    return "\n".join(lines)
