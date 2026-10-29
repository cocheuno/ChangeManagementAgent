"""Risk rubric from config/policy.yaml. History never includes the change itself."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from cm_agents.data.import_time import EASTERN, parse_utc

CHECKLIST = (
    "ordered_backout",
    "backout_trigger",
    "test_criteria",
    "implementation_owner",
)
RISK_VALUE = {"high": "2", "moderate": "3", "low": "4"}
IMPACT_VALUE = {1: "1", 2: "2", 3: "3"}
_DAY = timedelta(days=1)


def tier_name(score: int, policy: dict[str, Any]) -> str:
    thresholds = policy["risk"]["tiers"]
    if score >= int(thresholds["high"]):
        return "high"
    if score >= int(thresholds["moderate"]):
        return "moderate"
    return "low"


def impact_for_tier(tier: int) -> str:
    """Most-critical service tier: 1 High, 2 Medium, 3 Low. Matches task.impact."""
    return IMPACT_VALUE[tier]


def checklist_failures(quality: dict[str, bool]) -> int:
    return sum(1 for name in CHECKLIST if not quality.get(name, False))


def impacted_services(
    ci_names: list[str],
    ci_by_name: dict[str, dict[str, Any]],
    parents_of: dict[str, list[str]],
    *,
    depth: int = 3,
) -> list[str]:
    """Services of the affected CIs and of consumers up to `depth` hops.

    Relationships are stored as parent-depends-on-child. Walking to parents
    moves toward the consumers. Seeded service CIs are not in that graph, so
    the service is the catalog service of each CI reached.
    """
    seen = set(ci_names)
    frontier = list(ci_names)
    for _ in range(depth):
        nxt: list[str] = []
        for name in frontier:
            for parent in parents_of.get(name, []):
                if parent not in seen:
                    seen.add(parent)
                    nxt.append(parent)
        frontier = nxt
    services: list[str] = []
    for name in seen:
        service = str(ci_by_name.get(name, {}).get("service") or "")
        if service and service not in services:
            services.append(service)
    return services


def score_change(
    *,
    policy: dict[str, Any],
    change_type: str,
    deployment_method: str,
    start: datetime,
    end: datetime,
    service_tiers: list[int],
    similar_failure_rate: float | None,
    caused_incidents_90d: int,
    quality: dict[str, bool],
    inside_maintenance: bool,
) -> dict[str, Any]:
    factors = policy["risk"]["factors"]
    critical = min(service_tiers) if service_tiers else 3
    rows: list[tuple[str, int, str]] = []

    def add(name: str, points: int, evidence: str) -> None:
        rows.append((name, points, evidence))

    crit_points = int(factors["service_criticality"][f"tier{critical}"])
    add("service_criticality", crit_points, f"most critical tier {critical}")
    count = max(len(service_tiers), 1)
    if count <= 1:
        impacted = int(factors["impacted_services"]["1"])
        impacted_evidence = "1 impacted service"
    elif count == 2:
        impacted = int(factors["impacted_services"]["2"])
        impacted_evidence = "2 impacted services"
    else:
        impacted = int(factors["impacted_services"]["3+"])
        impacted_evidence = f"{count} impacted services"
    add("impacted_services", impacted, impacted_evidence)
    rate_points, rate_evidence = _rate_points(similar_failure_rate, factors)
    add("similar_change_failure_rate_12m", rate_points, rate_evidence)
    incident_points, incident_evidence = _incident_points(caused_incidents_90d, factors)
    add("change_caused_incidents_90d", incident_points, incident_evidence)
    method_points = int(factors["deployment_method"][deployment_method])
    add("deployment_method", method_points, deployment_method)
    outside = 0 if inside_maintenance else int(factors["outside_maintenance_window"])
    add(
        "outside_maintenance_window",
        outside,
        "inside the maintenance window" if inside_maintenance else "outside the maintenance window",
    )
    friday = _friday_evening(start)
    friday_points = int(factors["friday_evening_start"]) if friday else 0
    add(
        "friday_evening_start",
        friday_points,
        "Friday 15:00-23:59 ET" if friday else "not Friday evening",
    )
    failed = checklist_failures(quality)
    per_check = int(factors["plan_quality_failed_check"])
    add("plan_quality_failed_check", min(failed, 4) * per_check, f"{failed} checklist items failed")
    emergency_points = int(factors["emergency"]) if change_type == "emergency" else 0
    add("emergency", emergency_points, change_type)
    score = sum(points for _name, points, _evidence in rows)
    name = tier_name(score, policy)
    return {
        "score": score,
        "tier": name,
        "risk": RISK_VALUE[name],
        "impact": impact_for_tier(critical),
        "factors": [
            {"name": item, "points": points, "evidence": evidence}
            for item, points, evidence in rows
        ],
        "window_start": start,
        "window_end": end,
    }


def _rate_points(rate: float | None, factors: dict[str, Any]) -> tuple[int, str]:
    table = factors["similar_change_failure_rate_12m"]
    if rate is None:
        return int(table["lt_5pct"]), "no similar change in the prior 12 months"
    if rate < 0.05:
        return int(table["lt_5pct"]), f"similar failure rate {rate:.1%}"
    if rate <= 0.15:
        return int(table["5_to_15pct"]), f"similar failure rate {rate:.1%}"
    return int(table["gt_15pct"]), f"similar failure rate {rate:.1%}"


def _incident_points(count: int, factors: dict[str, Any]) -> tuple[int, str]:
    table = factors["change_caused_incidents_90d"]
    if count <= 0:
        return int(table["0"]), "0 change-caused incidents in 90 days"
    if count == 1:
        return int(table["1"]), "1 change-caused incident in 90 days"
    return int(table["2+"]), f"{count} change-caused incidents in 90 days"


def _friday_evening(start: datetime) -> bool:
    local = start.astimezone(EASTERN)
    return local.weekday() == 4 and 15 <= local.hour <= 23


def score_historical(fixtures: dict[str, Any], policy: dict[str, Any]) -> list[dict[str, Any]]:
    """Score the 1,500 historical changes. Features use only earlier instants."""
    changes = [row for row in fixtures["changes"] if row["kind"] == "historical"]
    ci_by_name = {row["name"]: row for row in fixtures["cis"]}
    parents_of: dict[str, list[str]] = defaultdict(list)
    for link in fixtures["relationships"]:
        parents_of[link["child"]].append(link["parent"])
    affected: dict[str, list[str]] = defaultdict(list)
    for link in fixtures["task_ci"]:
        affected[link["change"]].append(link["ci"])
    by_key = {row["key"]: row for row in fixtures["changes"]}
    caused: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for incident in fixtures["incidents"]:
        if incident.get("caused_by"):
            caused[incident["caused_by"]].append(incident)
    tiers = {row["name"]: int(row["tier"]) for row in fixtures["services"]}
    scored: list[dict[str, Any]] = []
    for change in sorted(changes, key=lambda row: row["start_date"] or row["opened_at"]):
        as_of = parse_utc(change["start_date"] or change["opened_at"])
        names = affected.get(change["key"]) or [change["cmdb_ci"]]
        services = impacted_services(names, ci_by_name, parents_of)
        if change["service"] not in services:
            services.append(change["service"])
        service_tiers = [tiers[name] for name in services if name in tiers]
        rate = _similar_rate(change, as_of, changes, caused)
        incidents = _caused_in_window(change, as_of, by_key, fixtures["incidents"])
        start = as_of
        end = parse_utc(change["end_date"]) if change["end_date"] else start
        inside = _inside_maintenance(start, end, min(service_tiers) if service_tiers else 3)
        result = score_change(
            policy=policy,
            change_type=change["type"],
            deployment_method=change["deployment_method"],
            start=start,
            end=end,
            service_tiers=service_tiers,
            similar_failure_rate=rate,
            caused_incidents_90d=incidents,
            quality=change["plan_quality"],
            inside_maintenance=inside,
        )
        failed = _failed(change, caused.get(change["key"], []))
        result["key"] = change["key"]
        result["failed"] = failed
        scored.append(result)
    return scored


def failure_table(scored: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for name in ("low", "moderate", "high"):
        group = [row for row in scored if row["tier"] == name]
        failed = sum(1 for row in group if row["failed"])
        rate = (failed / len(group)) if group else None
        rows.append({"tier": name, "count": len(group), "failed": failed, "rate": rate})
    return rows


def backtest_passes(table: list[dict[str, Any]]) -> bool:
    by_name = {row["tier"]: row for row in table}
    low, moderate, high = by_name["low"], by_name["moderate"], by_name["high"]
    if not low["count"] or not moderate["count"] or not high["count"]:
        return False
    if low["rate"] is None or moderate["rate"] is None or high["rate"] is None:
        return False
    between = low["rate"] < moderate["rate"] < high["rate"] or (
        high["rate"] < moderate["rate"] < low["rate"]
    )
    return high["rate"] >= 3 * low["rate"] and between


def history_features(
    fixtures: dict[str, Any],
    *,
    service: str,
    ci_class: str,
    as_of: datetime,
) -> tuple[float | None, int]:
    """Similar-change rate and 90-day caused incidents known before `as_of`."""
    changes = [row for row in fixtures["changes"] if row["kind"] == "historical"]
    by_key = {row["key"]: row for row in fixtures["changes"]}
    caused: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for incident in fixtures["incidents"]:
        if incident.get("caused_by"):
            caused[incident["caused_by"]].append(incident)
    probe = {"key": "", "service": service, "ci_class": ci_class, "state": "-5"}
    rate = _similar_rate(probe, as_of, changes, caused)
    incidents = _caused_in_window(probe, as_of, by_key, fixtures["incidents"])
    return rate, incidents


def _similar_rate(
    change: dict[str, Any],
    as_of: datetime,
    changes: list[dict[str, Any]],
    caused: dict[str, list[dict[str, Any]]],
) -> float | None:
    window_start = (as_of - timedelta(days=365)).strftime("%Y-%m-%d %H:%M:%S")
    as_of_text = as_of.strftime("%Y-%m-%d %H:%M:%S")
    observed = []
    for prior in changes:
        if prior["key"] == change["key"]:
            continue
        if prior["service"] != change["service"] or prior["ci_class"] != change["ci_class"]:
            continue
        closed = prior.get("closed_at") or ""
        if not closed or closed >= as_of_text or closed < window_start:
            continue
        if prior["state"] == "4":
            continue
        observed.append(_failed(prior, _incidents_before(caused.get(prior["key"], []), as_of_text)))
    if not observed:
        return None
    return sum(1 for failed in observed if failed) / len(observed)


def _incidents_before(incidents: list[dict[str, Any]], as_of_text: str) -> list[dict[str, Any]]:
    return [row for row in incidents if (row.get("opened_at") or "") < as_of_text]


def _caused_in_window(
    change: dict[str, Any],
    as_of: datetime,
    by_key: dict[str, dict[str, Any]],
    incidents: list[dict[str, Any]],
) -> int:
    start = (as_of - timedelta(days=90)).strftime("%Y-%m-%d %H:%M:%S")
    as_of_text = as_of.strftime("%Y-%m-%d %H:%M:%S")
    count = 0
    for incident in incidents:
        opened = incident.get("opened_at") or ""
        cause = incident.get("caused_by") or ""
        if not cause or not opened or opened < start or opened >= as_of_text:
            continue
        source = by_key.get(cause)
        if source and source.get("service") == change["service"]:
            count += 1
    return count


def _failed(change: dict[str, Any], incidents: list[dict[str, Any]]) -> bool:
    if change.get("close_code") == "unsuccessful":
        return True
    return any(incident.get("caused_by") == change["key"] for incident in incidents)


def _inside_maintenance(start: datetime, end: datetime, tier: int) -> bool:
    from cm_agents.enablement.windows import inside_maintenance

    return inside_maintenance(start, end, tier)
