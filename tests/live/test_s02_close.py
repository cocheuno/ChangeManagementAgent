"""S02 continues past go/no-go and closes successful. The durability test stays separate."""

from __future__ import annotations

import uuid

from cm_agents.servicenow.changes import find_by_correlation, read_change
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings
from tests.helpers.approve_as_human import approve_pending_once
from tests.live.support import approved_deploy_now, fields, run_cli, start_scenario


def test_s02_closes_successful_after_each_approval_and_a_go() -> None:
    thread = f"SYN-S02C-{uuid.uuid4().hex[:8]}"
    started = start_scenario("S02.yaml", thread)
    print(started.stdout)
    assert started.returncode == 0, started.stderr
    paused = fields(started.stdout)
    assert paused["interrupt"] == "authorization"
    assert paused["step"] == "assess"
    settings = load_settings()
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as agent:
        record = find_by_correlation(agent, thread)
    assert record is not None
    change_id = str(record["sys_id"])
    assert approve_pending_once(change_id) == "-3"
    authorized = run_cli("resume", thread)
    print(authorized.stdout)
    assert authorized.returncode == 0, authorized.stderr
    waiting = fields(authorized.stdout)
    assert waiting["interrupt"] == "authorization"
    assert waiting["step"] == "authorize"
    assert approve_pending_once(change_id) == "-2"
    ready = run_cli("resume", thread)
    print(ready.stdout)
    assert ready.returncode == 0, ready.stderr
    gate = fields(ready.stdout)
    assert gate["interrupt"] == "go_no_go"
    deploy_now = approved_deploy_now(change_id)
    print(f"s02 deploy now {deploy_now}")
    closed = run_cli(
        "resume",
        thread,
        "--decision",
        "go",
        "--by",
        "SYN Service Desk",
        "--reason",
        "the window is approved",
        "--now",
        deploy_now,
    )
    print(closed.stdout)
    print(closed.stderr)
    assert closed.returncode == 0, closed.stderr
    done = fields(closed.stdout)
    assert done["interrupt"] == "none"
    assert done["state"] == "3"
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as admin:
        current = read_change(admin, change_id)
        print(
            f"s02 number={current.get('number')} state={current.get('state')} "
            f"risk={current.get('risk')} close_code={current.get('close_code')}"
        )
        assert str(current.get("state")) == "3"
        assert str(current.get("risk")) == "4"
        assert str(current.get("close_code")) == "successful"
        tasks = admin.get_table(
            "change_task",
            query=f"change_request={change_id}^change_task_type=implementation",
            fields=["state"],
            limit=10,
        )
        assert any(str(row.get("state")) == "3" for row in tasks)
