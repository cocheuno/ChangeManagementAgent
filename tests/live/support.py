"""Subprocess helpers for the Phase 2 gate. Not part of the unit suite."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from cm_agents.servicenow.client import ServiceNowClient, ServiceNowError
from cm_agents.settings import repo_root


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    if not env.get("UV_PROJECT_ENVIRONMENT"):
        local = os.environ.get("LOCALAPPDATA", "")
        env["UV_PROJECT_ENVIRONMENT"] = str(Path(local) / "venvs" / "ChangeManagementAgent")
    env.setdefault("CM_AGENTS_RUN", "phase2-gate")
    executable = Path(sys.executable).with_name("cm-agents.exe")
    return subprocess.run(
        [str(executable), *args],
        cwd=repo_root(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def delete_change(admin: ServiceNowClient, change_id: str) -> None:
    for table, query in (
        ("sysapproval_approver", f"sysapproval={change_id}"),
        ("sysapproval_group", f"parent={change_id}"),
        ("change_task", f"change_request={change_id}^ORparent={change_id}"),
        ("task_ci", f"task={change_id}"),
        ("task_cmdb_ci_service", f"task={change_id}"),
        ("conflict", f"change={change_id}^ORconflicting_change={change_id}"),
    ):
        try:
            rows = admin.get_table(table, query=query, fields=["sys_id"], limit=50)
        except ServiceNowError:
            continue
        for row in rows:
            try:
                admin.delete_record(table, str(row["sys_id"]))
            except ServiceNowError as exc:
                if exc.status_code != 404:
                    raise
    try:
        admin.delete_record("change_request", change_id)
    except ServiceNowError as exc:
        if exc.status_code != 404:
            raise


def start_scenario(filename: str, thread: str) -> subprocess.CompletedProcess[str]:
    path = repo_root() / "scenarios" / filename
    return run_cli("change", "new", "--file", str(path), "--thread", thread)


def fields(stdout: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in stdout.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key in {"thread", "interrupt", "step", "change", "state", "error"}:
            found[key] = value.strip()
    return found
