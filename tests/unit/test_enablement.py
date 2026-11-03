from datetime import datetime, timedelta

from cm_agents.data.import_time import EASTERN, UTC
from cm_agents.enablement.resolve import resolution_gap, resolve_ci_name
from cm_agents.enablement.risk_score import checklist_failures, score_change, tier_name
from cm_agents.enablement.route import (
    authority_steps,
    route_after_authorization,
    route_after_schedule,
)
from cm_agents.enablement.windows import (
    blocks,
    deployment_blocked_by_policy,
    earliest_window,
    freeze_hit,
    inside_maintenance,
    lead_time_met,
)

POLICY = {
    "risk": {
        "factors": {
            "service_criticality": {"tier1": 3, "tier2": 2, "tier3": 1},
            "impacted_services": {"1": 0, "2": 2, "3+": 3},
            "similar_change_failure_rate_12m": {"lt_5pct": 0, "5_to_15pct": 2, "gt_15pct": 3},
            "change_caused_incidents_90d": {"0": 0, "1": 1, "2+": 2},
            "deployment_method": {"automated": 0, "manual": 2},
            "outside_maintenance_window": 2,
            "friday_evening_start": 1,
            "plan_quality_failed_check": 1,
            "emergency": 2,
        },
        "tiers": {"high": 10, "moderate": 6},
    },
    "change_authority": {
        "normal_low": {"assess": "assignment_group", "authorize": "cab_approval"},
        "normal_high": {"assess": "assignment_group", "authorize": "cab_approval"},
        "emergency": {"authorize": "cab_approval"},
    },
}
STRONG = {
    "ordered_backout": True,
    "backout_trigger": True,
    "test_criteria": True,
    "implementation_owner": True,
}
FREEZES = [
    {"name": "SYN Month-End Close Freeze", "services": ["SYN Payments"]},
    {"name": "SYN Holiday Peak Freeze", "services": "all"},
]


def test_ci_resolution_prefers_an_exact_name() -> None:
    names = ["syn-hr-portal", "syn-hr-portal-extra"]
    assert resolve_ci_name("syn-hr-portal", names) == ["syn-hr-portal"]
    assert resolution_gap("syn-hr-portal", ["syn-hr-portal"]) is None


def test_ci_resolution_asks_when_a_contains_match_is_ambiguous() -> None:
    matches = resolve_ci_name("PAY", ["syn-pay-api", "syn-pay-ledger"])
    assert resolution_gap("PAY", matches) is not None
    assert resolve_ci_name("missing", ["syn-hr-portal"]) == []


def test_normal_authority_is_two_steps_and_emergency_is_one() -> None:
    assert authority_steps(POLICY, "normal", "low") == [
        ("assess", "assignment_group"),
        ("authorize", "cab_approval"),
    ]
    assert authority_steps(POLICY, "emergency", "high") == [("authorize", "cab_approval")]
    assert route_after_schedule("standard") == "ready"
    assert route_after_schedule("normal") == "risk"
    assert (
        route_after_authorization(
            change_type="normal", pending_step="assess", rejected=False, release_member=False
        )
        == "authorization"
    )
    assert (
        route_after_authorization(
            change_type="normal", pending_step="authorize", rejected=False, release_member=False
        )
        == "authorization"
    )
    assert (
        route_after_authorization(
            change_type="normal", pending_step=None, rejected=False, release_member=False
        )
        == "go_no_go"
    )
    assert (
        route_after_authorization(
            change_type="emergency", pending_step=None, rejected=False, release_member=False
        )
        == "authorized"
    )


def test_tier1_saturday_window_is_inside_maintenance() -> None:
    start = datetime(2026, 11, 7, 22, 0, tzinfo=EASTERN).astimezone(UTC)
    end = start + timedelta(hours=2)
    assert inside_maintenance(start, end, 1)
    tuesday = datetime(2026, 11, 3, 10, 0, tzinfo=EASTERN).astimezone(UTC)
    assert not inside_maintenance(tuesday, tuesday + timedelta(hours=2), 1)
    assert deployment_blocked_by_policy("standard", start, end, 1) is False
    assert deployment_blocked_by_policy("normal", start, end, 1) is False
    assert deployment_blocked_by_policy("standard", tuesday, tuesday + timedelta(hours=2), 1)


def test_payments_month_end_friday_is_a_freeze_and_the_next_window_is_later() -> None:
    start = datetime(2026, 10, 30, 18, 0, tzinfo=EASTERN).astimezone(UTC)
    end = start + timedelta(hours=2)
    assert freeze_hit("SYN Payments", start, end, FREEZES) == "SYN Month-End Close Freeze"
    assert freeze_hit("SYN HR Portal", start, end, FREEZES) is None
    now = datetime(2026, 10, 30, 16, 0, tzinfo=EASTERN).astimezone(UTC)
    found = earliest_window(
        now=now,
        duration=timedelta(hours=2),
        tier=1,
        service="SYN Payments",
        lead_business_days=0,
        freezes=FREEZES,
        occupied=[],
    )
    assert found is not None
    assert found[0] > start
    assert freeze_hit("SYN Payments", found[0], found[1], FREEZES) is None
    assert inside_maintenance(found[0], found[1], 1)


def test_lead_time_counts_weekdays_only() -> None:
    now = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)  # Thursday
    friday = datetime(2026, 10, 30, 18, 0, tzinfo=EASTERN).astimezone(UTC)
    assert not lead_time_met(now, friday, 5)
    later = datetime(2026, 11, 7, 22, 0, tzinfo=EASTERN).astimezone(UTC)
    assert lead_time_met(now, later, 5)


def test_a_normal_change_outside_maintenance_is_not_blocked_for_that_reason() -> None:
    now = datetime(2026, 10, 1, tzinfo=UTC)
    start = datetime(2026, 11, 3, 10, 0, tzinfo=EASTERN).astimezone(UTC)
    reasons = blocks(
        now=now,
        start=start,
        end=start + timedelta(hours=2),
        change_type="normal",
        tier=3,
        service="SYN HR Portal",
        lead_business_days=2,
        freezes=FREEZES,
        schedule_conflict=False,
    )
    assert reasons == []
    standard = blocks(
        now=now,
        start=start,
        end=start + timedelta(hours=2),
        change_type="standard",
        tier=3,
        service="SYN HR Portal",
        lead_business_days=0,
        freezes=FREEZES,
        schedule_conflict=False,
    )
    assert standard == ["outside maintenance window"]


def test_rubric_maps_score_to_the_policy_tiers() -> None:
    assert tier_name(10, POLICY) == "high"
    assert tier_name(6, POLICY) == "moderate"
    assert tier_name(5, POLICY) == "low"
    start = datetime(2026, 11, 7, 22, 0, tzinfo=EASTERN).astimezone(UTC)
    scored = score_change(
        policy=POLICY,
        change_type="normal",
        deployment_method="automated",
        start=start,
        end=start + timedelta(hours=2),
        service_tiers=[3],
        similar_failure_rate=None,
        caused_incidents_90d=0,
        quality=STRONG,
        inside_maintenance=True,
    )
    assert scored["tier"] == "low"
    assert scored["risk"] == "4"
    assert scored["impact"] == "3"
    assert checklist_failures(STRONG) == 0
