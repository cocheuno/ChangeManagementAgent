"""S06. Readiness fails before authorization, then all four stages pass."""

from __future__ import annotations

import uuid

import yaml

from cm_agents.agents.release import MODEL_TASK_NAMES, NOTE_SECTIONS, notes_path
from cm_agents.servicenow.changes import (
    STATE_ASSESS,
    STATE_AUTHORIZE,
    STATE_SCHEDULED,
    approval_groups_for,
    attach_affected,
    change_tasks,
    create_change,
    exact_ci,
    group_id,
    group_name,
    move_state,
    read_change,
    remember_change,
    update_fields,
    write_dates,
    write_risk,
)
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings, repo_root
from tests.helpers.approve_as_human import approve_every_step, approve_pending_once
from tests.live.support import approved_deploy_now, fields, run_cli


def _plans(ci: str) -> dict[str, str]:
    return {
        "justification": f"Publish the 2026.11.0 build of {ci} with the Online Store release.",
        "description": f"Member change for {ci} in release 2026.11.0.",
        "implementation_plan": (
            f"1. Owner SYN Store DevOps drains {ci}. "
            f"2. Owner SYN Store DevOps deploys the 2026.11.0 build to {ci}. "
            f"3. Owner SYN Store DevOps confirms the health check on {ci}."
        ),
        "backout_plan": (
            f"1. Trigger the backout when the health check on {ci} fails "
            "or the error rate exceeds 2 percent. "
            f"2. Owner SYN Store DevOps restores the previous build on {ci}. "
            "3. The backout finishes within 15 minutes. "
            f"4. Owner SYN Store DevOps confirms the previous build on {ci} is serving traffic."
        ),
        "test_plan": (
            f"1. Call the health endpoint on {ci}. "
            "2. Success criteria: HTTP 200 and the error rate stays under 2 percent for 5 minutes."
        ),
    }


def _create_member(
    agent: ServiceNowClient,
    thread: str,
    release_id: str,
    spec: dict,
    start: str,
    end: str,
    group: str,
) -> str:
    ci_name = str(spec["ci"])
    found = [row for row in exact_ci(agent, ci_name) if row.get("name") == ci_name]
    assert len(found) == 1, ci_name
    ci_id = str(found[0]["sys_id"])
    plans = _plans(ci_name)
    record = create_change(
        agent,
        "normal",
        {
            "short_description": str(spec["summary"]),
            "description": plans["description"],
            "correlation_id": f"{thread}-{ci_name}",
        },
    )
    sys_id = str(record["sys_id"])
    remember_change(sys_id, f"{thread}-{ci_name}")
    update_fields(
        agent,
        sys_id,
        {
            "assignment_group": group,
            "cmdb_ci": ci_id,
            "parent": release_id,
            "justification": plans["justification"],
            "implementation_plan": plans["implementation_plan"],
            "backout_plan": plans["backout_plan"],
            "test_plan": plans["test_plan"],
        },
    )
    attach_affected(agent, sys_id, [ci_id])
    write_dates(agent, sys_id, start, end)
    write_risk(agent, sys_id, "4", "1")
    return sys_id


def _group_names(admin: ServiceNowClient, change_id: str) -> list[str]:
    return [
        group_name(admin, str(row.get("assignment_group") or ""))
        for row in approval_groups_for(admin, change_id)
    ]


def test_s06_release_readiness_then_four_stages() -> None:
    scenario = yaml.safe_load((repo_root() / "scenarios" / "S06.yaml").read_text(encoding="utf-8"))
    thread = f"SYN-S06-{uuid.uuid4().hex[:8]}"
    start = str(scenario["window_start"])
    end = str(scenario["window_end"])
    created = run_cli(
        "release",
        "new",
        "--service",
        str(scenario["service"]),
        "--version",
        str(scenario["version"]),
        "--window",
        start,
        end,
        "--thread",
        thread,
    )
    print(created.stdout)
    assert created.returncode == 0, created.stderr
    opened = fields(created.stdout)
    assert opened["step"] == "created"
    assert opened["state"] == "-5"
    settings = load_settings()
    awaiting_id = ""
    awaiting_number = ""
    member_ids: list[str] = []
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as agent:
        release = agent.get_table(
            "change_request",
            query=f"correlation_id={thread}",
            fields=["sys_id", "number", "state"],
            limit=2,
        )
        assert len(release) == 1
        release_id = str(release[0]["sys_id"])
        release_number = str(release[0]["number"])
        print(f"s06 release {release_number} state={release[0].get('state')}")
        group = group_id(agent, str(scenario["assignment_group"]))
        for spec in scenario["members"]:
            sys_id = _create_member(agent, thread, release_id, spec, start, end, group)
            member_ids.append(sys_id)
            if spec["await_authorization"]:
                move_state(agent, "normal", sys_id, STATE_ASSESS)
                approve_pending_once(sys_id)
                current = read_change(agent, sys_id)
                assert str(current.get("state")) == STATE_AUTHORIZE
                write_risk(agent, sys_id, "4", "1")
                awaiting_id = sys_id
                awaiting_number = str(current.get("number") or "")
            else:
                move_state(agent, "normal", sys_id, STATE_ASSESS)
                approve_every_step(sys_id)
                current = read_change(agent, sys_id)
                assert str(current.get("state")) == STATE_SCHEDULED
                write_risk(agent, sys_id, "4", "1")
            stored = read_change(agent, sys_id)
            assert str(stored.get("risk")) == "4"
            print(
                f"s06 member {stored.get('number')} state={stored.get('state')} "
                f"risk={stored.get('risk')}"
            )
    assert awaiting_number
    started = run_cli("release", "run", "--thread", thread)
    print(started.stdout)
    assert started.returncode == 0, started.stderr
    paused = fields(started.stdout)
    assert paused["interrupt"] == "requester_info"
    assert paused["step"] == "readiness"
    assert paused["state"] == "-5"
    assert awaiting_number in paused["detail"]
    assert "authorization check" in paused["detail"]
    assert "awaiting authorization" in paused["detail"]
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=60,
    ) as agent:
        still_new = read_change(agent, release_id)
        assert str(still_new.get("state")) == "-5"
        print(f"s06 readiness held {still_new.get('number')} in New")
    approve_pending_once(awaiting_id)
    assessed = run_cli("resume", thread)
    print(assessed.stdout)
    assert assessed.returncode == 0, assessed.stderr
    assess = fields(assessed.stdout)
    assert assess["interrupt"] == "authorization"
    assert assess["step"] == "assess"
    assert assess["state"] == "-4"
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=60,
    ) as admin:
        names = _group_names(admin, release_id)
        print(f"s06 assess groups={names}")
        assert "Change Management" in names
    approve_pending_once(release_id)
    authorized = run_cli("resume", thread)
    print(authorized.stdout)
    assert authorized.returncode == 0, authorized.stderr
    authorize = fields(authorized.stdout)
    assert authorize["interrupt"] == "authorization"
    assert authorize["step"] == "authorize"
    assert authorize["state"] == "-3"
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_admin_user,
        settings.sn_admin_password,
        secrets=settings.secret_values(),
        timeout=60,
    ) as admin:
        names = _group_names(admin, release_id)
        print(f"s06 authorize groups={names}")
        assert "CAB Approval" in names
    approve_pending_once(release_id)
    go_wait = run_cli("resume", thread)
    print(go_wait.stdout)
    assert go_wait.returncode == 0, go_wait.stderr
    waiting = fields(go_wait.stdout)
    assert waiting["interrupt"] == "go_no_go"
    assert waiting["step"] == "go_no_go"
    assert waiting["state"] == "-2"
    moment = approved_deploy_now(release_id)
    finished = run_cli(
        "resume",
        thread,
        "--decision",
        "go",
        "--by",
        "Release Manager",
        "--reason",
        "Members are authorized and the four stages are clear",
        "--now",
        moment,
    )
    print(finished.stdout)
    assert finished.returncode == 0, finished.stderr
    done = fields(finished.stdout)
    assert done["interrupt"] == "none"
    assert done["step"] == "closed"
    assert done["state"] == "3"
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as agent:
        release_row = read_change(agent, release_id)
        print(
            f"s06 closed {release_row.get('number')} state={release_row.get('state')} "
            f"risk={release_row.get('risk')} close_code={release_row.get('close_code')}"
        )
        assert str(release_row.get("state")) == "3"
        assert str(release_row.get("close_code")) == "successful"
        assert str(release_row.get("risk")) == "4"
        tasks = change_tasks(agent, release_id)
        print(f"s06 release tasks={len(tasks)}")
        stage_tasks = []
        model_names = []
        for task in tasks:
            name = str(task.get("short_description") or "")
            blob = f"{task.get('description') or ''} {task.get('close_notes') or ''}"
            print(
                f"s06 task {name} type={task.get('change_task_type')} "
                f"state={task.get('state')} result={blob.strip()}"
            )
            if name in MODEL_TASK_NAMES:
                assert str(task.get("state")) == "4"
                model_names.append(name)
                continue
            assert name.startswith("SYN ")
            assert task.get("change_task_type") == "implementation"
            assert str(task.get("state")) == "3"
            assert "result=passed" in blob
            stage_tasks.append(task)
        assert set(model_names) == set(MODEL_TASK_NAMES)
        names = {str(task.get("short_description") or "") for task in stage_tasks}
        assert names == {
            "SYN DEV implementation",
            "SYN TEST implementation",
            "SYN STAGE implementation",
            "SYN PROD implementation",
        }
        for sys_id in member_ids:
            member = read_change(agent, sys_id)
            member_tasks = change_tasks(agent, sys_id)
            member_model = []
            print(
                f"s06 member {member.get('number')} state={member.get('state')} "
                f"close_code={member.get('close_code')} tasks={len(member_tasks)} "
                f"notes={member.get('close_notes')}"
            )
            for task in member_tasks:
                name = str(task.get("short_description") or "")
                print(
                    f"s06 member task {member.get('number')} {name} "
                    f"type={task.get('change_task_type')} state={task.get('state')}"
                )
                assert not name.startswith("SYN ")
                assert name in MODEL_TASK_NAMES
                assert str(task.get("state")) == "4"
                member_model.append(name)
            assert str(member.get("state")) == "3"
            assert str(member.get("close_code")) == "successful"
            assert release_number in str(member.get("close_notes") or "")
            assert set(member_model) == set(MODEL_TASK_NAMES)
    notes = notes_path(str(scenario["version"])).read_text(encoding="utf-8")
    print(f"s06 notes file {notes_path(str(scenario['version'])).name}")
    for heading in NOTE_SECTIONS:
        print(f"s06 section {heading!r} present={heading in notes}")
        assert heading in notes
