from pathlib import Path

import yaml

from cm_agents.data.generate import TIER1_SCHEDULE, TIER23_SCHEDULE


def test_change_authority_matches_discovery() -> None:
    path = Path(__file__).resolve().parents[2] / "config" / "policy.yaml"
    policy = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert policy["change_authority"] == {
        "standard": "pre_authorized",
        "normal_low": "assignment_group",
        "normal_moderate": "assignment_group",
        "normal_high": "assignment_group",
        "emergency": "cab_approval",
    }
    assert policy["timezone"] == "America/New_York"
    assert policy["risk"]["tiers"] == {"high": 10, "moderate": 6}
    assert policy["maintenance_windows"]["tier1"] == TIER1_SCHEDULE
    assert policy["maintenance_windows"]["tier2_3"] == TIER23_SCHEDULE
    assert len(policy["freezes"]) == 2
