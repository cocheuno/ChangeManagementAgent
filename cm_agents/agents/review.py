"""Close a change and write a PIR when policy requires one.

The model writes the narrative. The close code, the timeline, and the action
owners are checked in code.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from cm_agents.agents.context import current
from cm_agents.audit import audit_path
from cm_agents.llm import complete, record_block
from cm_agents.servicenow.changes import (
    STATE_CLOSED,
    STATE_NEW,
    STATE_REVIEW,
    ChangeError,
    approval_comments,
    journal,
    move_state,
    read_change,
    update_fields,
    write_note,
)
from cm_agents.servicenow.client import ServiceNowError
from cm_agents.settings import repo_root


class PirAction(BaseModel):
    action: str
    owner: str


class PirDraft(BaseModel):
    what_went_well: str
    what_did_not: str
    root_cause_hypothesis: str
    actions: list[PirAction] = Field(default_factory=list)


def run_review(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("error"):
        return {}
    if (state.get("review") or {}).get("done"):
        return {}
    ctx = current()
    record = read_change(ctx.client, state["change_sys_id"])
    rejected = str((state.get("authorization") or {}).get("route") or "") == "rejected"
    deployment = state.get("deployment") or {}
    if rejected and deployment.get("outcome") not in {"verified", "rolled_back"}:
        return _rejection(state, record)
    code = _close_code(deployment)
    notes = str(deployment.get("close_notes") or "").strip() or f"Deployment outcome {code}."
    if str(record.get("state") or "") != STATE_REVIEW:
        return {
            "error": f"review expected state {STATE_REVIEW} and found {record.get('state')}",
            "review": {"done": False, "change_state": str(record.get("state") or "")},
        }
    updated = update_fields(
        ctx.client,
        state["change_sys_id"],
        {"close_code": code, "close_notes": notes[:4000]},
    )
    if str(updated.get("close_code") or "") != code:
        raise ChangeError(f"close_code read back {updated.get('close_code')} after writing {code}")
    record = move_state(ctx.client, state["change_type"], state["change_sys_id"], STATE_CLOSED)
    if str(record.get("state") or "") != STATE_CLOSED:
        raise ChangeError(f"state is {record.get('state')} after a move to Closed")
    if str(record.get("close_code") or "") != code:
        raise ChangeError(f"closed change close_code is {record.get('close_code')}")
    _note(state, "closed", f"close code {code}")
    pir = ""
    if _pir_required(state, code, deployment):
        pir = _write_pir(state, record, code)
    return {
        "review": {
            "done": True,
            "route": "closed",
            "close_code": code,
            "change_state": str(record.get("state") or ""),
            "pir": pir,
        }
    }


def _rejection(state: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    comments = approval_comments(current().client, state["change_sys_id"])
    reason = comments[-1] if comments else "an approver rejected the change"
    _note(state, "rejected", reason)
    if str(record.get("state") or "") not in {STATE_REVIEW, STATE_CLOSED, STATE_NEW}:
        try:
            record = move_state(
                current().client, state["change_type"], state["change_sys_id"], STATE_REVIEW
            )
        except (ServiceNowError, ChangeError):
            record = read_change(current().client, state["change_sys_id"])
    pir = ""
    if _pir_required(state, "unsuccessful", state.get("deployment") or {}):
        pir = _write_pir(state, record, "unsuccessful")
    return {
        "review": {
            "done": True,
            "route": "recorded",
            "close_code": "",
            "change_state": str(record.get("state") or ""),
            "pir": pir,
        }
    }


def _close_code(deployment: dict[str, Any]) -> str:
    outcome = str(deployment.get("outcome") or "")
    priority = str(deployment.get("priority") or "")
    if outcome == "rolled_back" or priority in {"1", "2", "3"}:
        return "unsuccessful"
    if priority == "4":
        return "successful_issues"
    return "successful"


def _pir_required(state: dict[str, Any], close_code: str, deployment: dict[str, Any]) -> bool:
    reasons = set(current().policy.get("pir_required_when") or [])
    if close_code == "unsuccessful" and "unsuccessful" in reasons:
        return True
    if state.get("change_type") == "emergency" and "emergency" in reasons:
        return True
    if str((state.get("risk") or {}).get("tier") or "") == "high" and "high_risk" in reasons:
        return True
    return bool(deployment.get("incident")) and "caused_incident" in reasons


def _write_pir(state: dict[str, Any], record: dict[str, Any], close_code: str) -> str:
    number = str(record.get("number") or state.get("change_number") or "change")
    owners = [str(row["user_name"]) for row in current().fixtures.get("users") or []]
    owner_text = "\n".join(owners)
    draft = complete(
        current().settings,
        PirDraft,
        system=(
            "Write a post-implementation review from the timeline. "
            "Choose every action owner from the supplied user list. "
            "Label the root cause as a hypothesis. Make no state decision."
        ),
        user=record_block(
            "\n".join(
                [
                    f"change {number}",
                    f"close code {close_code}",
                    "timeline:",
                    *_timeline(state),
                    "owners:",
                    owner_text,
                ]
            )
        ),
        thread_id=state["thread_id"],
        agent="review",
        action="pir",
        record=number,
    )
    chosen = _with_real_owners(draft, owners)
    path = repo_root() / "reports" / "pir" / f"{number}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_markdown(number, chosen, state), encoding="utf-8")
    return str(path)


def _with_real_owners(draft: PirDraft, owners: list[str]) -> PirDraft:
    fallback = owners[0] if owners else ""
    actions = []
    for action in draft.actions:
        owner = action.owner if action.owner in owners else fallback
        actions.append(PirAction(action=action.action, owner=owner))
    if not actions and fallback:
        actions.append(PirAction(action="Review the deployment record", owner=fallback))
    return draft.model_copy(update={"actions": actions})


def _timeline(state: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    path = audit_path()
    if path.is_file():
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            row = json.loads(raw)
            if row.get("thread_id") != state.get("thread_id"):
                continue
            lines.append(
                f"{row.get('ts')} {row.get('agent')} {row.get('action')} {row.get('outcome')}"
            )
    for text in journal(current().client, state["change_sys_id"]):
        lines.append(f"work note: {text}")
    for text in approval_comments(current().client, state["change_sys_id"]):
        lines.append(f"approval comment: {text}")
    return lines


def _markdown(number: str, draft: PirDraft, state: dict[str, Any]) -> str:
    actions = "\n".join(f"- {row.owner}: {row.action}" for row in draft.actions)
    timeline = "\n".join(f"- {line}" for line in _timeline(state))
    return (
        f"# PIR {number}\n\n"
        "## Timeline\n"
        f"{timeline}\n\n"
        "## What went well\n"
        f"{draft.what_went_well}\n\n"
        "## What didn't\n"
        f"{draft.what_did_not}\n\n"
        "## Root-cause hypothesis\n"
        f"Hypothesis: {draft.root_cause_hypothesis}\n\n"
        "## Actions\n"
        f"{actions}\n"
    )


def _note(state: dict[str, Any], decision: str, reason: str) -> None:
    marker = f"[agent:review] {decision}:"
    if any(marker in text for text in journal(current().client, state["change_sys_id"])):
        return
    write_note(
        current().client,
        state["change_sys_id"],
        thread_id=state["thread_id"],
        agent="review",
        decision=decision,
        reason=reason,
        record=str(state.get("change_number") or ""),
    )
