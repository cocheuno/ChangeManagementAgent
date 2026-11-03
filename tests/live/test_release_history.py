"""The 20 seeded releases carry planned end and actual end. No model calls."""

from __future__ import annotations

import json
from datetime import datetime

from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings, repo_root


def _parse(value: str) -> datetime:
    return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")


def test_seeded_releases_carry_planned_and_actual_ends() -> None:
    root = repo_root()
    fixtures = json.loads(
        (root / "data" / "synthetic" / "fixtures.json").read_text(encoding="utf-8")
    )
    ground = json.loads(
        (root / "data" / "synthetic" / "ground_truth.json").read_text(encoding="utf-8")
    )
    expected = [row for row in fixtures["changes"] if row.get("release")]
    expected_on_time = sum(
        1 for row in expected if _parse(row["work_end"]) <= _parse(row["end_date"])
    )
    settings = load_settings()
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as client:
        rows = client.get_table(
            "change_request",
            query="correlation_idSTARTSWITHSYN-REL-",
            fields=["number", "short_description", "correlation_id", "end_date", "work_end"],
            limit=50,
        )
    releases = [
        row
        for row in rows
        if str(row.get("short_description") or "").startswith("SYN RELEASE ")
        and str(row.get("correlation_id") or "").startswith("SYN-REL-")
    ]
    missing = [
        str(row.get("number") or "")
        for row in releases
        if not row.get("end_date") or not row.get("work_end")
    ]
    on_time = [
        row
        for row in releases
        if row.get("end_date")
        and row.get("work_end")
        and _parse(str(row["work_end"])) <= _parse(str(row["end_date"]))
    ]
    late = [row for row in releases if row not in on_time]
    print(
        f"ground_truth releases={len(expected)} on_time={expected_on_time} "
        f"pct={ground['metrics']['release_on_time_pct']}"
    )
    print(
        f"servicenow releases={len(releases)} with_both_dates={len(releases) - len(missing)} "
        f"on_time={len(on_time)}"
    )
    for row in late:
        print(
            f"late {row.get('number')} {row.get('short_description')} "
            f"end_date={row.get('end_date')} work_end={row.get('work_end')}"
        )
    assert len(expected) == 20
    assert expected_on_time == 17
    assert ground["metrics"]["release_on_time_pct"] == 85.0
    assert missing == []
    assert len(releases) == 20
    assert len(on_time) == 17
