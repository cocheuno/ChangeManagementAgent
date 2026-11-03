"""S03: CAB rejects a high-risk change. Nothing is implemented."""

from __future__ import annotations

import uuid

from cm_agents.servicenow.changes import find_by_correlation, journal, read_change
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings, repo_root
from tests.helpers.approve_as_human import approve_pending_once, reject_pending_once
from tests.live.support import fields, run_cli, start_scenario


def test_s03_cab_rejection_is_recorded_without_implementation() -> None:
    thread = f"SYN-S03-{uuid.uuid4().hex[:8]}"
    started = start_scenario("S03.yaml", thread)
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
    assert waiting["step"] == "authorize"
    reject_pending_once(change_id, "SYN reject: backout is not acceptable")
    reviewed = run_cli("resume", thread)
    print(reviewed.stdout)
    print(reviewed.stderr)
    assert reviewed.returncode == 0, reviewed.stderr
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as admin:
        current = read_change(admin, change_id)
        notes = journal(admin, change_id)
        print(
            f"s03 number={current.get('number')} state={current.get('state')} "
            f"risk={current.get('risk')} start={current.get('start_date')}"
        )
        for text in notes:
            print(f"s03 note {text}")
        assert str(current.get("risk")) == "2"
        assert str(current.get("start_date")) > "2026-10-30 22:00:00"
        assert any("freeze" in text.lower() for text in notes)
        assert any("[agent:review] rejected:" in text for text in notes)
        tasks = admin.get_table(
            "change_task",
            query=f"change_request={change_id}^change_task_type=implementation",
            fields=["sys_id"],
            limit=10,
        )
        assert tasks == []
        number = str(current.get("number") or "")
    pir = repo_root() / "reports" / "pir" / f"{number}.md"
    assert pir.is_file()
    assert "Hypothesis:" in pir.read_text(encoding="utf-8")
