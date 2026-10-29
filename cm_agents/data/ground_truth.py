"""Metrics and patterns computed from the fixture document.

This is a separate path from the metrics agent, which reads ServiceNow. Pattern
rates for P1-P4 ignore release changes. Volume and on-time metrics include them.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from cm_agents.data.import_time import EASTERN, UTC

_FORMAT = "%Y-%m-%d %H:%M:%S"


def build_ground_truth(fixtures: dict[str, Any]) -> dict[str, Any]:
    changes = fixtures["changes"]
    incidents = fixtures["incidents"]
    start = _parse(fixtures["history_start"])
    end = _parse(fixtures["anchor"])
    period = [
        row
        for row in changes
        if start <= _parse(row["opened_at"]) < end
    ]
    implemented = [row for row in period if row["state"] == "3"]
    pattern_rows = [row for row in implemented if not row["release"]]
    caused_changes = {
        row["caused_by"]
        for row in incidents
        if str(row.get("caused_by", "")).startswith("SYN-CHG")
        or str(row.get("caused_by", "")).startswith("SYN-REL")
    }
    weeks = (end - start).total_seconds() / (7 * 24 * 3600)
    candidates = _candidates(pattern_rows, caused_changes)
    return {
        "anchor": fixtures["anchor"],
        "period": {"start": fixtures["history_start"], "end": fixtures["anchor"]},
        "patterns": {
            "p1": _p1(pattern_rows),
            "p2": _p2(pattern_rows),
            "p3": _p3(pattern_rows),
            "p4": _p4(pattern_rows),
            "p5": _p5(changes, incidents),
            "p6": {"count": len(candidates), "signatures": candidates},
        },
        "metrics": {
            "volume_by_type": _count(period, "type"),
            "volume_by_service": _count(period, "service"),
            "volume_by_month": _count_month(period),
            "success_rate_pct": _success_pct(implemented),
            "success_rate_by_type": {
                change_type: _success_pct(
                    [row for row in implemented if row["type"] == change_type]
                )
                for change_type in ("standard", "normal", "emergency")
            },
            "failure_rate_pct": _failure_pct(implemented, caused_changes),
            "emergency_ratio_pct": _share_pct(period, "emergency"),
            "standard_share_pct": _share_pct(period, "standard"),
            "lead_time_hours": _lead_time(implemented),
            "deployment_frequency_per_week": _frequency(implemented, weeks),
            "mttr_hours": _mttr(incidents),
            "release_on_time_pct": _release_on_time(changes),
        },
        "standard_change_candidates": [row["signature"] for row in candidates],
        "notes": {
            "caused_by": (
                "fixture field caused_by is stored in incident.u_caused_by; "
                "incident.parent is not used"
            ),
            "patterns_exclude_releases": True,
            "risk_tier_selects_approver": False,
        },
    }


def write_ground_truth(document: dict[str, Any], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(document, indent=2, sort_keys=True) + "\n"
    (directory / "ground_truth.json").write_text(payload, encoding="utf-8")


def _parse(text: str) -> datetime:
    return datetime.strptime(text, _FORMAT).replace(tzinfo=UTC)


def _pct(part: int, whole: int) -> float:
    if whole == 0:
        return 0.0
    return round(100 * part / whole, 1)


def _count(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows:
        key = str(row[field])
        totals[key] = totals.get(key, 0) + 1
    return totals


def _count_month(rows: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows:
        key = row["opened_at"][:7]
        totals[key] = totals.get(key, 0) + 1
    return totals


def _failed(row: dict[str, Any], caused_changes: set[str]) -> bool:
    return row["close_code"] == "unsuccessful" or row["key"] in caused_changes


def _success_pct(rows: list[dict[str, Any]]) -> float:
    ok = sum(1 for row in rows if row["close_code"] in {"successful", "successful_issues"})
    return _pct(ok, len(rows))


def _failure_pct(rows: list[dict[str, Any]], caused_changes: set[str]) -> float:
    failed = sum(1 for row in rows if _failed(row, caused_changes))
    return _pct(failed, len(rows))


def _share_pct(rows: list[dict[str, Any]], change_type: str) -> float:
    matched = sum(1 for row in rows if row["type"] == change_type)
    return _pct(matched, len(rows))


def _failure_rate(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0
    failed = sum(1 for row in rows if row["close_code"] == "unsuccessful")
    return round(100 * failed / len(rows), 1)


def _p1(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    payments = [row for row in rows if row["type"] == "normal" and row["payments_db"]]
    baseline = [row for row in rows if row["type"] == "normal" and not row["payments_db"]]
    return {
        "payments_count": len(payments),
        "payments_failure_pct": _failure_rate(payments),
        "baseline_count": len(baseline),
        "baseline_failure_pct": _failure_rate(baseline),
    }


def _friday(row: dict[str, Any]) -> bool:
    if not row["work_start"]:
        return False
    local = _parse(row["work_start"]).astimezone(EASTERN)
    return local.weekday() == 4 and 15 <= local.hour <= 23


def _p2(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    friday = [row for row in rows if _friday(row)]
    other = [row for row in rows if not _friday(row)]
    return {
        "friday_count": len(friday),
        "friday_failure_pct": _failure_rate(friday),
        "other_count": len(other),
        "other_failure_pct": _failure_rate(other),
    }


def _p3(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    manual = [row for row in rows if row["deployment_method"] == "manual"]
    automated = [row for row in rows if row["deployment_method"] == "automated"]
    return {
        "manual_count": len(manual),
        "manual_failure_pct": _failure_rate(manual),
        "automated_count": len(automated),
        "automated_failure_pct": _failure_rate(automated),
    }


def _p4(rows: list[dict[str, Any]]) -> dict[str, float | int]:
    group = [row for row in rows if row["assignment_group"] == "SYN Fulfillment DevOps"]
    weak = [row for row in group if not row["plan_quality"]["ordered_backout"]]
    strong = [row for row in group if row["plan_quality"]["ordered_backout"]]
    weak_rate = _failure_rate(weak)
    strong_rate = _failure_rate(strong)
    ratio = round(weak_rate / strong_rate, 2) if strong_rate else 0.0
    return {
        "count": len(group),
        "weak_count": len(weak),
        "weak_share_pct": _pct(len(weak), len(group)),
        "weak_failure_pct": weak_rate,
        "strong_failure_pct": strong_rate,
        "ratio": ratio,
    }


def _p5(changes: list[dict[str, Any]], incidents: list[dict[str, Any]]) -> dict[str, float | int]:
    priority = {row["key"]: row["priority"] for row in incidents}
    emergencies = [row for row in changes if row["type"] == "emergency"]
    linked = [
        row
        for row in emergencies
        if priority.get(row["parent"]) in {"1", "2"}
    ]
    return {
        "emergency_count": len(emergencies),
        "linked_count": len(linked),
        "linked_pct": _pct(len(linked), len(emergencies)),
    }


def _signature(row: dict[str, Any]) -> str:
    return " ".join(row["short_description"].lower().split())


def _candidates(
    rows: list[dict[str, Any]], caused_changes: set[str]
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row["type"] != "normal":
            continue
        key = (_signature(row), row["ci_class"], row["assignment_group"])
        groups.setdefault(key, []).append(row)
    found = []
    for (signature, ci_class, group), members in groups.items():
        failures = sum(1 for row in members if row["close_code"] == "unsuccessful")
        caused = sum(1 for row in members if row["key"] in caused_changes)
        if len(members) >= 10 and failures == 0 and caused == 0:
            found.append(
                {
                    "signature": signature,
                    "ci_class": ci_class,
                    "assignment_group": group,
                    "executions": len(members),
                    "failures": failures,
                    "caused_incidents": caused,
                }
            )
    found.sort(key=lambda row: (row["signature"], row["ci_class"], row["assignment_group"]))
    return found


def _lead_time(rows: list[dict[str, Any]]) -> float:
    hours = []
    for row in rows:
        if not row["work_end"]:
            continue
        delta = _parse(row["work_end"]) - _parse(row["opened_at"])
        hours.append(delta.total_seconds() / 3600)
    return round(_median(hours), 1)


def _frequency(rows: list[dict[str, Any]], weeks: float) -> dict[str, float]:
    totals: dict[str, int] = {}
    for row in rows:
        if row["environment"] != "prod":
            continue
        totals[row["service"]] = totals.get(row["service"], 0) + 1
    return {service: round(count / weeks, 1) for service, count in sorted(totals.items())}


def _mttr(incidents: list[dict[str, Any]]) -> float:
    hours = []
    for row in incidents:
        caused = str(row.get("caused_by", "")).startswith("SYN-CHG") or str(
            row.get("caused_by", "")
        ).startswith("SYN-REL")
        if caused and row["opened_at"] and row["resolved_at"]:
            delta = _parse(row["resolved_at"]) - _parse(row["opened_at"])
            hours.append(delta.total_seconds() / 3600)
    return round(_median(hours), 1)


def _release_on_time(changes: list[dict[str, Any]]) -> float:
    releases = [row for row in changes if row["release"]]
    on_time = sum(1 for row in releases if _parse(row["work_end"]) <= _parse(row["end_date"]))
    return _pct(on_time, len(releases))


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
