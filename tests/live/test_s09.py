"""S09 and S10. Metrics and standard-change candidates from ServiceNow."""

from __future__ import annotations

import json

import yaml

from cm_agents.agents.metrics import unknown_numbers
from cm_agents.data.queries import STD_TEMPLATE
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings, repo_root
from tests.live.support import run_cli


def _scenario(name: str) -> dict:
    path = repo_root() / "scenarios" / name
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError(f"{name} must be a mapping")
    return loaded


def test_s09_and_s10_match_ground_truth(capsys) -> None:
    s09 = _scenario("S09.yaml")
    s10 = _scenario("S10.yaml")
    assert s09["from"] == s10["from"]
    assert s09["to"] == s10["to"]
    truth = json.loads(
        (repo_root() / "data" / "synthetic" / "ground_truth.json").read_text(encoding="utf-8")
    )
    finished = run_cli(
        "report",
        "metrics",
        "--period",
        str(s09["period"]),
        "--from",
        str(s09["from"]),
        "--to",
        str(s09["to"]),
    )
    print(finished.stdout)
    assert finished.returncode == 0, finished.stderr
    payload = json.loads(finished.stdout)
    assert payload["metrics"] == truth["metrics"]
    comparable = [
        {key: value for key, value in row.items() if key != "proposed_template"}
        for row in payload["candidates"]
    ]
    assert comparable == truth["patterns"]["p6"]["signatures"]
    signatures = [row["signature"] for row in payload["candidates"]]
    assert signatures == truth["standard_change_candidates"]
    report = repo_root() / "reports" / "metrics" / f"{s09['period']}.md"
    text = report.read_text(encoding="utf-8")
    commentary = text.split("## Commentary", 1)[1].split("## Standard change candidates", 1)[0]
    table = {
        "period_end": s09["to"],
        "period_start": s09["from"],
        **payload["metrics"],
    }
    assert unknown_numbers(commentary, table) == []
    settings = load_settings()
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as agent:
        templates = agent.get_table(
            "std_change_record_producer",
            query=STD_TEMPLATE,
            fields=["name"],
            limit=20,
        )
        names = {str(row.get("name") or "") for row in templates}
        print(f"s10 templates={sorted(names)}")
        for row in payload["candidates"]:
            print(
                f"s10 candidate {row['signature']} executions={row['executions']} "
                f"failures={row['failures']} caused={row['caused_incidents']} "
                f"template={row['proposed_template']}"
            )
            assert row["proposed_template"] not in names
        task_query = (
            "change_request.correlation_idSTARTSWITHSYN-CHG-"
            "^ORchange_request.correlation_idSTARTSWITHSYN-OPEN-"
            "^ORchange_request.correlation_idSTARTSWITHSYN-REL-"
        )
        counted = agent.count("change_task", task_query)
        print(f"s09 seed change_task count={counted}")
        assert counted == 0
    captured = capsys.readouterr()
    assert "s09 seed change_task count=0" in captured.out
    print(captured.out)
