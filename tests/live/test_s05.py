"""S05: an emergency change deploys after CAB approval, with no go/no-go."""

from __future__ import annotations

import uuid

from cm_agents.servicenow.changes import exact_ci, find_by_correlation, find_incident, read_change
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings, repo_root
from tests.helpers.approve_as_human import approve_pending_once
from tests.live.support import fields, run_cli, start_scenario

TRIGGER = "SYN-SCN-S05-trigger"


def test_s05_emergency_closes_after_cab_approval() -> None:
    settings = load_settings()
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as agent:
        _ensure_trigger(agent)
        thread = f"SYN-S05-{uuid.uuid4().hex[:8]}"
        started = start_scenario("S05.yaml", thread)
        print(started.stdout)
        print(started.stderr)
        assert started.returncode == 0, started.stderr
        paused = fields(started.stdout)
        assert paused["interrupt"] == "authorization"
        assert paused["step"] == "authorize"
        record = find_by_correlation(agent, thread)
        assert record is not None
        assert str(record.get("type")) == "emergency"
        change_id = str(record["sys_id"])
    assert approve_pending_once(change_id) == "-2"
    closed = run_cli("resume", thread, "--now", "2026-11-08 03:30:00")
    print(closed.stdout)
    print(closed.stderr)
    assert closed.returncode == 0, closed.stderr
    done = fields(closed.stdout)
    assert done["interrupt"] == "none"
    assert done["state"] == "3"
    assert "go_no_go" not in closed.stdout
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as admin:
        current = read_change(admin, change_id)
        print(
            f"s05 number={current.get('number')} type={current.get('type')} "
            f"state={current.get('state')} close_code={current.get('close_code')}"
        )
        assert str(current.get("state")) == "3"
        assert str(current.get("close_code")) == "successful"
        number = str(current.get("number") or "")
    pir = repo_root() / "reports" / "pir" / f"{number}.md"
    assert pir.is_file()


def _ensure_trigger(agent: ServiceNowClient) -> None:
    existing = find_incident(agent, TRIGGER)
    if existing and str(existing.get("state") or "") not in {"6", "7"}:
        incident_id = str(existing["sys_id"])
        print(
            f"s05 trigger exists priority={existing.get('priority')} "
            f"state={existing.get('state')}"
        )
        if str(existing.get("priority") or "") in {"1", "2"}:
            return
    else:
        cis = exact_ci(agent, "syn-store-checkout")
        assert len(cis) == 1
        created = agent.create_record(
            "incident",
            {
                "short_description": "SYN S05 checkout P1",
                "correlation_id": TRIGGER,
                "cmdb_ci": cis[0]["sys_id"],
                "impact": "1",
                "urgency": "1",
                "state": "1",
            },
        )
        incident_id = str(created["sys_id"])
    # Priority is a lookup from impact and urgency. Do not write priority.
    agent.update_record(
        "incident",
        incident_id,
        {"impact": "1", "urgency": "1", "state": "1"},
    )
    stored = agent.get_record(
        "incident",
        incident_id,
        fields=["number", "priority", "impact", "urgency", "state"],
    )
    print(
        f"s05 trigger number={stored.get('number')} priority={stored.get('priority')} "
        f"impact={stored.get('impact')} urgency={stored.get('urgency')} "
        f"state={stored.get('state')}"
    )
    assert str(stored.get("priority") or "") in {"1", "2"}
