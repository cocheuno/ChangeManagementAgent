"""Move a change to the approval state and wait. This agent never writes approvals."""

from __future__ import annotations

import re
import time
from typing import Any, Literal

from pydantic import BaseModel

from cm_agents.agents.context import current
from cm_agents.enablement.route import authority_steps, route_after_authorization
from cm_agents.llm import complete, record_block
from cm_agents.servicenow.changes import (
    STATE_ASSESS,
    STATE_AUTHORIZE,
    STATE_NEW,
    STATE_SCHEDULED,
    approval_groups_for,
    approvals_for,
    group_name,
    move_state,
    read_change,
    same_window,
    write_note,
)
from cm_agents.settings import repo_root

_SYS_ID = re.compile(r"\b[0-9a-f]{32}\b")
_STATE_FOR_STEP = {"assess": STATE_ASSESS, "authorize": STATE_AUTHORIZE}


class CabBrief(BaseModel):
    summary_and_justification: str
    risk_and_services: str
    window_and_conflicts: str
    backout_readiness: str
    advisory: Literal["approve", "approve with conditions", "reject"]
    reasons: str


def run_authorization(state: dict[str, Any]) -> dict[str, Any]:
    ctx = current()
    record = read_change(ctx.client, state["change_sys_id"])
    steps = authority_steps(ctx.policy, state["change_type"], state["risk"]["tier"])
    approvals = approvals_for(ctx.client, state["change_sys_id"])
    groups = approval_groups_for(ctx.client, state["change_sys_id"])
    previous = dict(state.get("authorization") or {})
    number = str(state.get("change_number") or record.get("number") or "")
    if _rejected(record, approvals):
        if not previous.get("rejection_noted"):
            write_note(
                ctx.client,
                state["change_sys_id"],
                thread_id=state["thread_id"],
                agent="authorization",
                decision="rejected",
                reason="an approver rejected the change",
                record=number,
            )
        return {
            "authorization": {
                **previous,
                "route": "rejected",
                "pending_step": None,
                "change_state": str(record.get("state") or ""),
                "rejection_noted": True,
            }
        }
    if str(record.get("state") or "") == STATE_SCHEDULED or not steps:
        route = route_after_authorization(
            change_type=state["change_type"],
            pending_step=None,
            rejected=False,
            release_member=bool(state.get("release_member")),
        )
        if route == "go_no_go" and not previous.get("approved_noted"):
            write_note(
                ctx.client,
                state["change_sys_id"],
                thread_id=state["thread_id"],
                agent="authorization",
                decision="approved",
                reason="required approvals are approved and the change is Scheduled",
                record=number,
            )
        return {
            "authorization": {
                **previous,
                "route": route,
                "pending_step": None,
                "change_state": str(record.get("state") or ""),
                "approved_noted": True,
            }
        }
    step = _pending_step(str(record.get("state") or ""), steps)
    if str(record.get("state") or "") == STATE_NEW:
        step = steps[0][0]
        record = move_state(
            ctx.client,
            state["change_type"],
            state["change_sys_id"],
            _STATE_FOR_STEP[step],
        )
        time.sleep(2)
        approvals = approvals_for(ctx.client, state["change_sys_id"])
        groups = approval_groups_for(ctx.client, state["change_sys_id"])
    mismatch = _mismatch(ctx, step, groups, str(record.get("assignment_group") or ""))
    if mismatch and previous.get("mismatch") != mismatch:
        write_note(
            ctx.client,
            state["change_sys_id"],
            thread_id=state["thread_id"],
            agent="authorization",
            decision="mismatch",
            reason=mismatch,
            record=number,
        )
    brief_written = bool(previous.get("brief_written"))
    if not brief_written:
        _write_brief(state, record)
        brief_written = True
    if previous.get("noted_step") != step:
        authority = dict(steps)[step]
        write_note(
            ctx.client,
            state["change_sys_id"],
            thread_id=state["thread_id"],
            agent="authorization",
            decision="awaiting",
            reason=f"{step} approval from {authority}. The agent does not write approvals.",
            record=number,
        )
    return {
        "authorization": {
            "route": "authorization",
            "pending_step": step,
            "change_state": str(record.get("state") or ""),
            "brief_written": brief_written,
            "noted_step": step,
            "mismatch": mismatch,
            "approved_noted": False,
            "rejection_noted": False,
        }
    }


def finish_standard(state: dict[str, Any]) -> dict[str, Any]:
    ctx = current()
    record = read_change(ctx.client, state["change_sys_id"])
    if str(record.get("state") or "") != STATE_SCHEDULED:
        record = move_state(ctx.client, "standard", state["change_sys_id"], STATE_SCHEDULED)
    write_note(
        ctx.client,
        state["change_sys_id"],
        thread_id=state["thread_id"],
        agent="authorization",
        decision="scheduled",
        reason="standard change is pre-authorized and the window complies",
        record=str(state.get("change_number") or ""),
    )
    return {
        "authorization": {
            "route": "ready",
            "pending_step": None,
            "change_state": str(record.get("state") or ""),
        }
    }


def record_go_no_go(state: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    choice = str(decision.get("decision") or "")
    by = str(decision.get("by") or "")
    reason = str(decision.get("reason") or "")
    write_note(
        current().client,
        state["change_sys_id"],
        thread_id=state["thread_id"],
        agent="authorization",
        decision="go_no_go",
        reason=f"{choice} by {by}: {reason}",
        record=str(state.get("change_number") or ""),
    )
    previous = dict(state.get("authorization") or {})
    previous["go_no_go"] = {"decision": choice, "by": by, "reason": reason}
    previous["route"] = "recorded"
    return {"authorization": previous}


def _pending_step(state_value: str, steps: list[tuple[str, str]]) -> str:
    if state_value == STATE_ASSESS:
        return "assess"
    if state_value == STATE_AUTHORIZE:
        return "authorize"
    return steps[0][0]


def _rejected(record: dict[str, Any], approvals: list[dict[str, Any]]) -> bool:
    if str(record.get("approval") or "") == "rejected":
        return True
    return any(str(row.get("state") or "") == "rejected" for row in approvals)


def _mismatch(ctx: Any, step: str, groups: list[dict[str, Any]], assignment_group: str) -> str:
    if step == "assess":
        found = any(str(row.get("assignment_group") or "") == assignment_group for row in groups)
        if found:
            return ""
        return "Assess did not generate an approval for the change assignment group"
    names = [group_name(ctx.client, str(row.get("assignment_group") or "")) for row in groups]
    if "CAB Approval" in names:
        return ""
    return "Authorize did not generate a CAB Approval group approval"


def _write_brief(state: dict[str, Any], record: dict[str, Any]) -> None:
    ctx = current()
    schedule = state["schedule"]
    others = same_window(ctx.client, state["change_sys_id"], schedule["start"], schedule["end"])
    factors = "\n".join(
        f"- {row['name']}: {row['points']} ({row['evidence']})" for row in state["risk"]["factors"]
    )
    services = ", ".join(state.get("impacted_service_names") or [])
    facts = "\n".join(
        [
            f"Change {state.get('change_number')}",
            f"Summary: {state['request'].get('summary')}",
            f"Justification: {state['request'].get('justification')}",
            f"Risk tier: {state['risk']['tier']} score {state['risk']['score']}",
            f"Impacted services: {services}",
            f"Factors:\n{factors}",
            f"Window: {schedule['start']} to {schedule['end']} UTC",
            f"Requested window: {schedule['requested_start']} to {schedule['requested_end']} UTC",
            f"Maintenance: {schedule.get('maintenance')}",
            f"Conflict types: {', '.join(schedule.get('conflict_types') or []) or 'none'}",
            "Other active changes in the window:",
            "\n".join(others) or "none",
            "Backout plan:",
            str(state["request"].get("backout_plan") or ""),
            "Do not include a sys_id. The recommendation is advisory.",
        ]
    )
    system = (
        "You are the Change Authorization agent writing a CAB brief. "
        "Use only the facts in the record data. "
        "advisory is one of: approve, approve with conditions, reject. "
        "Every text section must be non-empty. Do not invent sys_ids, names, or approvals."
    )
    brief = _complete_brief(state, system, facts)
    number = str(state.get("change_number") or record.get("number") or state["change_sys_id"])
    path = repo_root() / "reports" / "cab" / f"{number}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown(number, brief), encoding="utf-8")


def _complete_brief(state: dict[str, Any], system: str, facts: str) -> CabBrief:
    ctx = current()
    user = record_block(facts)
    last: CabBrief | None = None
    for _ in range(2):
        last = complete(
            ctx.settings,
            CabBrief,
            system=system,
            user=user,
            thread_id=state["thread_id"],
            agent="authorization",
            action="cab_brief",
            record=str(state.get("change_number") or ""),
        )
        unknown = _unknown_ids(last, facts)
        empty = _empty_sections(last)
        if not unknown and not empty:
            return last
        user = record_block(facts) + f"\n\nFix these problems: {empty} {unknown}"
    raise RuntimeError("CAB brief still had an empty section or an unknown sys_id")


def _empty_sections(brief: CabBrief) -> str:
    names = [
        name
        for name in (
            "summary_and_justification",
            "risk_and_services",
            "window_and_conflicts",
            "backout_readiness",
            "reasons",
        )
        if not str(getattr(brief, name) or "").strip()
    ]
    return "empty sections: " + ", ".join(names) if names else ""


def _unknown_ids(brief: CabBrief, facts: str) -> str:
    allowed = set(_SYS_ID.findall(facts.casefold()))
    text = " ".join(
        [
            brief.summary_and_justification,
            brief.risk_and_services,
            brief.window_and_conflicts,
            brief.backout_readiness,
            brief.reasons,
        ]
    ).casefold()
    unknown = [found for found in _SYS_ID.findall(text) if found not in allowed]
    return "unknown sys_id: " + ", ".join(unknown) if unknown else ""


def _markdown(number: str, brief: CabBrief) -> str:
    return "\n".join(
        [
            f"# CAB brief {number}",
            "",
            "## Summary and justification",
            brief.summary_and_justification.strip(),
            "",
            "## Risk factors and impacted services",
            brief.risk_and_services.strip(),
            "",
            "## Window and conflicts",
            brief.window_and_conflicts.strip(),
            "",
            "## Backout readiness",
            brief.backout_readiness.strip(),
            "",
            "## Advisory recommendation",
            f"advisory: {brief.advisory}",
            brief.reasons.strip(),
            "",
        ]
    )
