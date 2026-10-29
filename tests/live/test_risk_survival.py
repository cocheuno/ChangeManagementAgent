"""A plain risk and impact write survives every state through Scheduled."""

from __future__ import annotations

import time
import uuid

from cm_agents.servicenow.changes import (
    STATE_ASSESS,
    STATE_AUTHORIZE,
    STATE_SCHEDULED,
    approvals_for,
    create_change,
    group_id,
    move_state,
    read_change,
    update_fields,
    write_risk,
)
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings
from tests.live.support import delete_change

PAIR = ("2", "1")


def test_plain_risk_write_survives_until_scheduled() -> None:
    settings = load_settings()
    thread = f"SYN-PROBE-RISK-{uuid.uuid4().hex[:8]}"
    agent = ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=120,
    )
    admin = ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=120,
    )
    change_id = ""
    try:
        created = create_change(
            agent,
            "normal",
            {
                "short_description": "SYN-PROBE-RISK survival",
                "description": "SYN-PROBE-RISK plain field update",
                "correlation_id": thread,
            },
        )
        change_id = str(created["sys_id"])
        update_fields(
            agent,
            change_id,
            {
                "assignment_group": group_id(agent, "SYN Platform Ops"),
                "start_date": "2026-12-12 03:00:00",
                "end_date": "2026-12-12 05:00:00",
            },
        )
        write_risk(agent, change_id, *PAIR)
        _expect(agent, change_id, "after write")
        move_state(agent, "normal", change_id, STATE_ASSESS)
        _expect(agent, change_id, "after Assess")
        _approve_until(admin, change_id, STATE_ASSESS)
        current = read_change(agent, change_id)
        print(f"after Assess approval state={current.get('state')}")
        assert str(current.get("state")) == STATE_AUTHORIZE
        _expect(agent, change_id, "after Authorize")
        _approve_until(admin, change_id, STATE_AUTHORIZE)
        current = read_change(agent, change_id)
        print(f"after CAB approval state={current.get('state')}")
        assert str(current.get("state")) == STATE_SCHEDULED
        _expect(agent, change_id, "after Scheduled")
    finally:
        if change_id:
            delete_change(admin, change_id)
        agent.close()
        admin.close()


def _expect(agent: ServiceNowClient, change_id: str, label: str) -> None:
    record = read_change(agent, change_id)
    pair = (str(record.get("risk") or ""), str(record.get("impact") or ""))
    print(f"{label} risk={pair[0]} impact={pair[1]} state={record.get('state')}")
    assert pair == PAIR, f"{label} recalculated risk to {pair[0]}/{pair[1]}"


def _approve_until(admin: ServiceNowClient, change_id: str, leaving: str) -> None:
    deadline = time.time() + 120
    approved: set[str] = set()
    while time.time() < deadline:
        record = read_change(admin, change_id)
        if str(record.get("state") or "") != leaving:
            return
        rows = [
            row
            for row in approvals_for(admin, change_id)
            if str(row.get("state") or "") == "requested"
        ]
        seen: set[str] = set()
        for row in rows:
            group = str(row.get("group") or row["sys_id"])
            if group in seen or str(row["sys_id"]) in approved:
                continue
            seen.add(group)
            admin.update_record("sysapproval_approver", str(row["sys_id"]), {"state": "approved"})
            approved.add(str(row["sys_id"]))
        time.sleep(3)
    raise AssertionError(f"state stayed {leaving}")
