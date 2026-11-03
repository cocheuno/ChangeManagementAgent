"""S07: canary failure rolls back, opens one incident, and does not redeploy PROD."""

from __future__ import annotations

import json
import os
import uuid

from cm_agents.audit import audit_path
from cm_agents.servicenow.changes import find_by_correlation, find_incident, read_change
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings
from tests.helpers.approve_as_human import approve_pending_once
from tests.live.support import approved_deploy_now, fields, print_pir, run_cli, start_scenario


def test_s07_failed_canary_rolls_back_without_a_second_prod_deploy() -> None:
    thread = f"SYN-S07-{uuid.uuid4().hex[:8]}"
    started = start_scenario("S07.yaml", thread)
    print(started.stdout)
    assert started.returncode == 0, started.stderr
    paused = fields(started.stdout)
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
    assert fields(authorized.stdout)["step"] == "authorize"
    assert approve_pending_once(change_id) == "-2"
    ready = run_cli("resume", thread)
    print(ready.stdout)
    assert ready.returncode == 0, ready.stderr
    assert fields(ready.stdout)["interrupt"] == "go_no_go"
    deploy_now = approved_deploy_now(change_id)
    print(f"s07 deploy now {deploy_now}")
    closed = run_cli(
        "resume",
        thread,
        "--decision",
        "go",
        "--by",
        "SYN Fulfillment DevOps",
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
        incident = find_incident(admin, thread)
        print(
            f"s07 number={current.get('number')} state={current.get('state')} "
            f"close_code={current.get('close_code')} incident={incident}"
        )
        assert str(current.get("state")) == "3"
        assert str(current.get("close_code")) == "unsuccessful"
        assert incident is not None
        stored = admin.get_record(
            "incident",
            str(incident["sys_id"]),
            fields=[
                "number",
                "priority",
                "impact",
                "urgency",
                "u_caused_by",
                "correlation_id",
            ],
        )
        print(
            f"s07 incident number={stored.get('number')} "
            f"sys_id={incident.get('sys_id')} "
            f"u_caused_by={stored.get('u_caused_by')} change_sys_id={change_id} "
            f"priority={stored.get('priority')} impact={stored.get('impact')} "
            f"urgency={stored.get('urgency')}"
        )
        assert str(stored.get("u_caused_by") or "") == change_id
        assert str(stored.get("correlation_id") or "") == thread
        assert str(stored.get("impact") or "") == "2"
        assert str(stored.get("urgency") or "") == "2"
        assert str(stored.get("priority") or "")
        number = str(current.get("number") or "")
    outcomes = _prod_steps(thread)
    print(f"s07 prod steps={outcomes}")
    assert outcomes
    failed_at = [index for index, text in enumerate(outcomes) if "result=failed" in text]
    assert failed_at
    assert failed_at[-1] == len(outcomes) - 1
    print_pir(number)


def _prod_steps(thread: str) -> list[str]:
    path = audit_path()
    assert path.is_file()
    run = os.environ.get("CM_AGENTS_RUN", "")
    outcomes = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if row.get("thread_id") != thread or row.get("action") != "deploy_step":
            continue
        if run and row.get("run") != run:
            continue
        outcome = str(row.get("outcome") or "")
        if outcome.startswith("env=PROD"):
            outcomes.append(outcome)
    return outcomes
