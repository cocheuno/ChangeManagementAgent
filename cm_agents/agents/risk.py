"""Score the window Scheduling kept. The model judges the checklist only."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from cm_agents.agents.context import current
from cm_agents.data.import_time import parse_utc
from cm_agents.enablement.risk_score import CHECKLIST, history_features, score_change
from cm_agents.enablement.windows import inside_maintenance
from cm_agents.llm import complete, record_block
from cm_agents.servicenow.changes import link_service, service_ci, write_note, write_risk


class PlanJudgment(BaseModel):
    ordered_backout: bool
    backout_trigger: bool
    test_criteria: bool
    implementation_owner: bool


def judge_plans(state: dict[str, Any]) -> dict[str, bool]:
    stored = state.get("checklist")
    if isinstance(stored, dict) and all(name in stored for name in CHECKLIST):
        return {name: bool(stored[name]) for name in CHECKLIST}
    ctx = current()
    request = state["request"]
    plans = "\n\n".join(
        [
            "Implementation plan:\n" + str(request.get("implementation_plan") or ""),
            "Backout plan:\n" + str(request.get("backout_plan") or ""),
            "Test plan:\n" + str(request.get("test_plan") or ""),
        ]
    )
    system = (
        "You are the Risk and Impact Assessment agent for Change Enablement. "
        "Return one boolean per checklist item. "
        "ordered_backout is true only when the backout plan has concrete ordered steps. "
        "backout_trigger is true only when it states when to trigger the backout "
        "and how long it takes. "
        "test_criteria is true only when the test plan has verification steps "
        "and success criteria. "
        "implementation_owner is true only when the implementation plan has "
        "ordered steps and an owner. "
        "Do not choose a risk tier and do not approve the change."
    )
    judged = complete(
        ctx.settings,
        PlanJudgment,
        system=system,
        user=record_block(plans),
        thread_id=state["thread_id"],
        agent="risk",
        action="plan_quality",
        record=str(state.get("change_number") or ""),
    )
    return {name: bool(getattr(judged, name)) for name in CHECKLIST}


def score_window(
    state: dict[str, Any],
    start_text: str,
    end_text: str,
    checklist: dict[str, bool],
) -> dict[str, Any]:
    ctx = current()
    start = parse_utc(start_text)
    end = parse_utc(end_text)
    tiers = _tiers(state)
    critical = min(tiers) if tiers else 3
    rate, incidents = history_features(
        ctx.fixtures,
        service=str(state.get("service") or ""),
        ci_class=_primary_class(state),
        as_of=start,
    )
    method = str(state["request"].get("deployment_method") or "automated")
    result = score_change(
        policy=ctx.policy,
        change_type=str(state.get("change_type") or "normal"),
        deployment_method=method,
        start=start,
        end=end,
        service_tiers=tiers,
        similar_failure_rate=rate,
        caused_incidents_90d=incidents,
        quality=checklist,
        inside_maintenance=inside_maintenance(start, end, critical),
    )
    result["window_start"] = start_text
    result["window_end"] = end_text
    return result


def run_risk(state: dict[str, Any]) -> dict[str, Any]:
    ctx = current()
    schedule = state["schedule"]
    checklist = judge_plans(state)
    result = score_window(state, schedule["start"], schedule["end"], checklist)
    written = write_risk(
        ctx.client,
        state["change_sys_id"],
        result["risk"],
        result["impact"],
    )
    if str(written.get("risk")) != result["risk"] or str(written.get("impact")) != result["impact"]:
        raise RuntimeError("risk write did not survive the read-back")
    links = _link_services(ctx, state)
    factors = "; ".join(
        f"{row['name']} {row['points']} ({row['evidence']})" for row in result["factors"]
    )
    write_note(
        ctx.client,
        state["change_sys_id"],
        thread_id=state["thread_id"],
        agent="risk",
        decision="scored",
        reason=(
            f"{result['tier']} score {result['score']}, risk {result['risk']}, "
            f"impact {result['impact']}. {factors}. service link {links}"
        ),
        record=str(state.get("change_number") or ""),
    )
    stored = {
        "score": result["score"],
        "tier": result["tier"],
        "risk": result["risk"],
        "impact": result["impact"],
        "factors": result["factors"],
    }
    return {"checklist": checklist, "risk": stored, "service_link": links}


def _tiers(state: dict[str, Any]) -> list[int]:
    ctx = current()
    by_name = {row["name"]: int(row["tier"]) for row in ctx.fixtures["services"]}
    names = list(state.get("impacted_service_names") or [])
    if state.get("service") and state["service"] not in names:
        names.append(state["service"])
    return [by_name[name] for name in names if name in by_name]


def _primary_class(state: dict[str, Any]) -> str:
    cis = state.get("affected_cis") or []
    if not cis:
        return ""
    name = cis[0]["name"]
    for row in current().fixtures["cis"]:
        if row["name"] == name:
            return str(row["ci_class"])
    return str(cis[0].get("ci_class") or "")


def _link_services(ctx: Any, state: dict[str, Any]) -> str:
    outcomes = []
    for name in state.get("impacted_service_names") or []:
        sys_id = service_ci(ctx.client, name)
        if not sys_id:
            outcomes.append(f"{name} missing")
            continue
        outcomes.append(f"{name} {link_service(ctx.client, state['change_sys_id'], sys_id)}")
    return ", ".join(outcomes) if outcomes else "none"
