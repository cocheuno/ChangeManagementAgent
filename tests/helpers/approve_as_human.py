"""Approve pending change steps with the admin account.

Agent code must not import this module. The helper approves one requested
approver in each pending group, then waits for the next step ServiceNow creates.
"""

from __future__ import annotations

import time

from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings


class ApprovalTimeout(RuntimeError):
    """The change did not reach Scheduled before the deadline."""


def approve_pending_once(change_sys_id: str, timeout_s: float = 180) -> str:
    """Approve one approver in the current step and wait until the state moves."""
    return _act_once(change_sys_id, "approved", "", timeout_s)


def reject_pending_once(change_sys_id: str, comment: str, timeout_s: float = 180) -> str:
    """Reject one approver in the current step and wait until the state moves."""
    return _act_once(change_sys_id, "rejected", comment, timeout_s)


def _act_once(change_sys_id: str, decision: str, comment: str, timeout_s: float) -> str:
    settings = load_settings()
    deadline = time.time() + timeout_s
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=60,
    ) as client:
        before = client.get_record("change_request", change_sys_id, fields=["state", "approval"])
        before_state = str(before.get("state") or "")
        rows = client.get_table(
            "sysapproval_approver",
            query=f"sysapproval={change_sys_id}^state=requested",
            fields=["sys_id", "group", "state"],
            limit=40,
        )
        if not rows:
            raise ApprovalTimeout(f"change {change_sys_id} has no requested approver")
        approver_id = str(rows[0]["sys_id"])
        fields = {"state": decision}
        if comment:
            fields["comments"] = comment
        client.update_record("sysapproval_approver", approver_id, fields)
        print(f"helper {decision} one {rows[0].get('group')}", flush=True)
        while time.time() < deadline:
            record = client.get_record(
                "change_request", change_sys_id, fields=["state", "approval"]
            )
            state = str(record.get("state") or "")
            approval = str(record.get("approval") or "")
            print(f"helper state={state} approval={approval}", flush=True)
            if state != before_state or (decision == "rejected" and approval == "rejected"):
                return state
            time.sleep(2)
    raise ApprovalTimeout(f"change {change_sys_id} did not leave {before_state}")


def approve_every_step(change_sys_id: str, timeout_s: float = 180) -> str:
    settings = load_settings()
    deadline = time.time() + timeout_s
    approved: set[str] = set()
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=60,
    ) as client:
        while time.time() < deadline:
            record = client.get_record(
                "change_request",
                change_sys_id,
                fields=["state", "approval"],
            )
            state = str(record.get("state") or "")
            print(f"helper state={state} approval={record.get('approval')}", flush=True)
            if state == "-2":
                return state
            rows = client.get_table(
                "sysapproval_approver",
                query=f"sysapproval={change_sys_id}^state=requested",
                fields=["sys_id", "group", "state"],
                limit=40,
            )
            seen_groups: set[str] = set()
            acted = False
            for row in rows:
                group = str(row.get("group") or row["sys_id"])
                if group in seen_groups:
                    continue
                seen_groups.add(group)
                approver_id = str(row["sys_id"])
                if approver_id in approved:
                    continue
                client.update_record("sysapproval_approver", approver_id, {"state": "approved"})
                approved.add(approver_id)
                acted = True
                print(f"helper approved one {group}", flush=True)
            time.sleep(4 if acted else 2)
    raise ApprovalTimeout(f"change {change_sys_id} did not reach Scheduled")
