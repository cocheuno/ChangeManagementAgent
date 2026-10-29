"""The checklist must agree with fixture labels on at least 90% of 200 judgments."""

from __future__ import annotations

import json

from cm_agents.agents.context import AgentContext, activate, reset
from cm_agents.agents.risk import judge_plans
from cm_agents.enablement.risk_score import CHECKLIST
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings, repo_root


def test_plan_quality_agrees_with_the_fixture_labels() -> None:
    settings = load_settings()
    fixtures = json.loads(
        (repo_root() / "data" / "synthetic" / "fixtures.json").read_text(encoding="utf-8")
    )
    sample = sorted(
        (row for row in fixtures["changes"] if row["kind"] == "historical"),
        key=lambda row: row["key"],
    )[:50]
    assert len(sample) == 50
    counts = {name: 0 for name in CHECKLIST}
    client = ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=120,
    )
    token = activate(AgentContext(settings, client, {}, fixtures))
    try:
        for row in sample:
            judged = judge_plans(
                {
                    "thread_id": f"SYN-PLAN-{row['key']}",
                    "change_number": row["key"],
                    "request": {
                        "implementation_plan": row["implementation_plan"],
                        "backout_plan": row["backout_plan"],
                        "test_plan": row["test_plan"],
                    },
                }
            )
            labels = row["plan_quality"]
            for name in CHECKLIST:
                if bool(judged[name]) == bool(labels[name]):
                    counts[name] += 1
    finally:
        reset(token)
        client.close()
    matched = sum(counts.values())
    for name in CHECKLIST:
        print(f"{name} matched={counts[name]}/50")
    print(f"matched={matched}/200")
    assert matched >= 180, f"plan quality agreed on {matched}/200"
