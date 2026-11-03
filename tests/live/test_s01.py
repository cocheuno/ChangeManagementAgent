"""S01: a standard change deploys inside the policy window and closes successful."""

from __future__ import annotations

import uuid

from cm_agents.servicenow.changes import find_by_correlation, read_change
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings
from tests.live.support import fields, start_scenario


def test_s01_standard_change_closes_successful() -> None:
    thread = f"SYN-S01-{uuid.uuid4().hex[:8]}"
    started = start_scenario("S01.yaml", thread)
    print(started.stdout)
    print(started.stderr)
    assert started.returncode == 0, started.stderr
    done = fields(started.stdout)
    assert done["interrupt"] == "none"
    assert done["state"] == "3"
    settings = load_settings()
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as admin:
        record = find_by_correlation(admin, thread)
        assert record is not None
        current = read_change(admin, str(record["sys_id"]))
        print(
            f"s01 number={current.get('number')} type={current.get('type')} "
            f"state={current.get('state')} close_code={current.get('close_code')} "
            f"start={current.get('start_date')}"
        )
        assert str(current.get("type")) == "standard"
        assert str(current.get("state")) == "3"
        assert str(current.get("close_code")) == "successful"
        assert str(current.get("start_date")) == "2026-11-08 03:00:00"
        approvals = admin.get_table(
            "sysapproval_approver",
            query=f"sysapproval={current['sys_id']}",
            fields=["sys_id"],
            limit=10,
        )
        assert approvals == []
        tasks = admin.get_table(
            "change_task",
            query=f"change_request={current['sys_id']}^change_task_type=implementation",
            fields=["state", "change_task_type"],
            limit=10,
        )
        assert tasks
        assert any(str(row.get("state")) == "3" for row in tasks)
