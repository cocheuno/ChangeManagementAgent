"""Two normal changes on one CI. Only the second window moves."""

from __future__ import annotations

import uuid

from cm_agents.servicenow.changes import find_by_correlation, journal
from cm_agents.servicenow.client import ServiceNowClient
from cm_agents.settings import load_settings
from tests.live.support import fields, start_scenario

WINDOW = ("2026-11-08 03:00:00", "2026-11-08 05:00:00")


def test_s04_moves_the_second_window_and_stops_for_authorization() -> None:
    first = f"SYN-S04A-{uuid.uuid4().hex[:8]}"
    second = f"SYN-S04B-{uuid.uuid4().hex[:8]}"
    started = start_scenario("S04a.yaml", first)
    followed = start_scenario("S04b.yaml", second)
    print(started.stdout)
    print(followed.stdout)
    assert started.returncode == 0, started.stderr
    assert followed.returncode == 0, followed.stderr
    first_view = fields(started.stdout)
    second_view = fields(followed.stdout)
    assert first_view["interrupt"] == "authorization"
    assert second_view["interrupt"] == "authorization"
    settings = load_settings()
    with ServiceNowClient(
        settings.sn_instance_url,
        settings.sn_agent_user,
        settings.sn_agent_password,
        secrets=settings.secret_values(),
        timeout=120,
    ) as agent:
        left = find_by_correlation(agent, first)
        right = find_by_correlation(agent, second)
        assert left is not None and right is not None
        print(
            f"s04 first {left.get('number')} {left.get('start_date')} {left.get('end_date')} "
            f"state={left.get('state')}"
        )
        print(
            f"s04 second {right.get('number')} {right.get('start_date')} {right.get('end_date')} "
            f"state={right.get('state')}"
        )
        for text in journal(agent, str(left["sys_id"])):
            if "[agent:scheduling]" in text:
                print(f"s04 first note {text}")
        for text in journal(agent, str(right["sys_id"])):
            if "[agent:scheduling]" in text:
                print(f"s04 second note {text}")
        assert (str(left.get("start_date")), str(left.get("end_date"))) == WINDOW
        assert (str(right.get("start_date")), str(right.get("end_date"))) != WINDOW
        assert str(right.get("start_date") or "") > WINDOW[0]
