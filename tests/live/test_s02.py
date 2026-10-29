"""Kill S02 at the authorization interrupt, approve, and resume in a new process."""

from __future__ import annotations

import uuid

from cm_agents.servicenow.changes import find_by_correlation, journal, read_change
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings
from tests.helpers.approve_as_human import approve_every_step
from tests.live.support import fields, run_cli, start_scenario


def test_s02_reaches_go_no_go_after_a_new_process_resumes() -> None:
    thread = f"SYN-S02-{uuid.uuid4().hex[:8]}"
    started = start_scenario("S02.yaml", thread)
    print(started.stdout)
    assert started.returncode == 0, started.stderr
    paused = fields(started.stdout)
    assert paused["interrupt"] == "authorization"
    assert paused["step"] == "assess"
    assert paused["state"] == "-4"
    settings = load_settings()
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as agent, ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as admin:
        record = find_by_correlation(agent, thread)
        assert record is not None
        change_id = str(record["sys_id"])
        print(
            f"s02 paused number={record.get('number')} risk={record.get('risk')} "
            f"impact={record.get('impact')} state={record.get('state')}"
        )
        for text in journal(admin, change_id):
            if "[agent:risk] scored:" in text:
                print(f"s02 score {text}")
    approve_every_step(change_id)
    resumed = run_cli("resume", thread)
    print(resumed.stdout)
    assert resumed.returncode == 0, resumed.stderr
    done = fields(resumed.stdout)
    assert done["interrupt"] == "go_no_go"
    assert done["step"] == "go_no_go"
    assert done["state"] == "-2"
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as agent:
        current = read_change(agent, change_id)
        print(
            f"s02 resumed number={current.get('number')} risk={current.get('risk')} "
            f"impact={current.get('impact')} state={current.get('state')}"
        )
        assert str(current.get("state")) == "-2"
        assert str(current.get("risk")) == "4"
