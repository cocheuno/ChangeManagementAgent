"""The integration user adds an affected CI to a change that is still New."""

from __future__ import annotations

import uuid

from cm_agents.servicenow.changes import (
    STATE_NEW,
    attach_affected,
    create_change,
    exact_ci,
    read_change,
)
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings
from tests.live.support import delete_change

MARKER = "SYN-PROBE-CI"


def test_integration_user_attaches_an_affected_ci_in_new() -> None:
    settings = load_settings()
    thread = f"{MARKER}-{uuid.uuid4().hex[:8]}"
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
                "short_description": f"{MARKER} affected CI",
                "description": f"{MARKER} Change API attach while New",
                "correlation_id": thread,
            },
        )
        change_id = str(created["sys_id"])
        assert str(created.get("state")) == STATE_NEW
        cis = exact_ci(agent, "syn-hr-portal")
        assert len(cis) == 1
        attach_affected(agent, change_id, [str(cis[0]["sys_id"])])
        links = agent.get_table(
            "task_ci",
            query=f"task={change_id}",
            fields=["ci_item"],
            limit=5,
        )
        again = read_change(agent, change_id)
        print(
            f"affected_ci count={len(links)} state={again.get('state')} "
            f"number={again.get('number')}"
        )
        assert len(links) == 1
        assert str(links[0].get("ci_item")) == str(cis[0]["sys_id"])
        assert str(again.get("state")) == STATE_NEW
    finally:
        if change_id:
            delete_change(admin, change_id)
        left = admin.get_table(
            "change_request",
            query=f"correlation_id={thread}",
            fields=["sys_id"],
            limit=2,
        )
        agent.close()
        admin.close()
        assert left == []
