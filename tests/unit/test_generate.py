from collections import Counter
from datetime import datetime

import pytest

from cm_agents.data.generate import ANCHOR, HISTORY_START, SIGNATURES, generate, write_fixtures
from cm_agents.data.ground_truth import build_ground_truth
from cm_agents.data.import_time import EASTERN, UTC

pytestmark = pytest.mark.filterwarnings("ignore")


@pytest.fixture(scope="module")
def fixtures() -> dict:
    return generate(42)


def test_same_seed_is_byte_identical_and_another_seed_is_not(tmp_path) -> None:
    first = generate(42)
    second = generate(42)
    left = write_fixtures(first, tmp_path / "a")
    right = write_fixtures(second, tmp_path / "b")
    assert left == right
    assert (tmp_path / "a" / "fixtures.json").read_bytes() == (
        tmp_path / "b" / "fixtures.json"
    ).read_bytes()
    assert write_fixtures(generate(7), tmp_path / "c") != left


def test_volumes_and_prefixes(fixtures: dict) -> None:
    changes = fixtures["changes"]
    historical = [row for row in changes if row["kind"] == "historical"]
    assert len(fixtures["cis"]) == 300
    assert len(fixtures["users"]) == 40
    assert len(fixtures["schedules"]) == 2
    assert len(fixtures["task_ci"]) == 2400
    assert 540 <= len(fixtures["relationships"]) <= 660
    assert len(historical) == 1500
    assert len([row for row in changes if row["kind"] == "open"]) == 25
    assert len([row for row in changes if row["release"]]) == 20
    assert len(fixtures["incidents"]) == 164
    kinds = Counter(row["type"] for row in historical)
    assert kinds == {"standard": 675, "normal": 705, "emergency": 120}
    assert sum(1 for row in historical if row["state"] == "4") == 45
    names = {row["name"] for row in fixtures["groups"]}
    assert names == {
        "SYN Release Management",
        "SYN Store DevOps",
        "SYN Payments DevOps",
        "SYN Fulfillment DevOps",
        "SYN Platform Ops",
        "SYN Service Desk",
    }
    assert all(row["user_name"].startswith("syn.") for row in fixtures["users"])
    assert all(row["email"].endswith("@example.com") for row in fixtures["users"])
    assert all("risk" not in row for row in changes)
    shared = next(row for row in fixtures["cis"] if row["name"] == "syn-shared-sqlclu-prd-01")
    assert shared["payments_db"] is True
    assert shared["schedule"].startswith("SYN Tier-1")
    assert all(
        row["cmdb_ci"] != "syn-shared-sqlclu-prd-01"
        for row in changes
        if row["kind"] == "open"
    )


def test_dates_stay_inside_the_fixed_window(fixtures: dict) -> None:
    for row in fixtures["changes"]:
        opened = _parse(row["opened_at"])
        if row["kind"] == "open":
            assert opened >= ANCHOR
            assert row["work_start"] == ""
            continue
        assert HISTORY_START <= opened < ANCHOR
        if row["work_start"]:
            assert HISTORY_START <= _parse(row["work_start"]) < ANCHOR
    closed = [row for row in fixtures["changes"] if row["state"] in {"3", "4"}]
    assert all(row["active"] is False for row in closed)
    assert all(row["approval"] == "approved" for row in fixtures["changes"] if row["state"] == "3")


def test_patterns_are_within_three_points(fixtures: dict) -> None:
    changes = [
        row
        for row in fixtures["changes"]
        if row["state"] == "3" and not row["release"]
    ]
    payments = [row for row in changes if row["type"] == "normal" and row["payments_db"]]
    baseline = [row for row in changes if row["type"] == "normal" and not row["payments_db"]]
    assert abs(_fail_pct(payments) - 20) <= 3
    assert abs(_fail_pct(baseline) - 7) <= 3

    friday = [row for row in changes if _friday(row)]
    other = [row for row in changes if not _friday(row)]
    assert abs(_fail_pct(friday) - 2 * _fail_pct(other)) <= 3

    manual = [row for row in changes if row["deployment_method"] == "manual"]
    automated = [row for row in changes if row["deployment_method"] == "automated"]
    assert abs(_fail_pct(manual) - 3 * _fail_pct(automated)) <= 3

    fulfillment = [row for row in changes if row["assignment_group"] == "SYN Fulfillment DevOps"]
    weak = [row for row in fulfillment if not row["plan_quality"]["ordered_backout"]]
    strong = [row for row in fulfillment if row["plan_quality"]["ordered_backout"]]
    assert abs(100 * len(weak) / len(fulfillment) - 30) <= 3
    assert abs(_fail_pct(weak) - 2.5 * _fail_pct(strong)) <= 3
    assert all(row["backout_plan"] == "Revert if needed." for row in weak)
    assert all("Trigger:" in row["backout_plan"] for row in strong)
    assert all(row["implementation_plan"].startswith("Deployment method:") for row in changes)

    emergencies = [row for row in fixtures["changes"] if row["type"] == "emergency"]
    priority = {row["key"]: row["priority"] for row in fixtures["incidents"]}
    linked = [row for row in emergencies if priority.get(row["parent"]) in {"1", "2"}]
    assert abs(100 * len(linked) / len(emergencies) - 70) <= 3

    caused = {
        row["parent"]
        for row in fixtures["incidents"]
        if row["parent"].startswith("SYN-CHG") or row["parent"].startswith("SYN-REL")
    }
    signatures = []
    for text, ci_class, group, _service in SIGNATURES:
        rows = [
            row
            for row in changes
            if row["short_description"] == text
            and row["ci_class"] == ci_class
            and row["assignment_group"] == group
        ]
        assert len(rows) >= 10
        assert all(row["close_code"] == "successful" for row in rows)
        assert all(row["key"] not in caused for row in rows)
        signatures.append(" ".join(text.lower().split()))
    assert len(signatures) == 12

    by_type = {}
    for change_type, target in (("standard", 98), ("normal", 92), ("emergency", 85)):
        rows = [row for row in changes if row["type"] == change_type]
        ok = sum(1 for row in rows if row["close_code"] in {"successful", "successful_issues"})
        by_type[change_type] = 100 * ok / len(rows)
        assert abs(by_type[change_type] - target) <= 3


def test_release_membership_and_ground_truth(fixtures: dict) -> None:
    releases = [row for row in fixtures["changes"] if row["release"]]
    children = Counter(
        row["parent"] for row in fixtures["changes"] if row["parent"].startswith("SYN-REL")
    )
    assert set(children) == {row["key"] for row in releases}
    assert set(children.values()) == {4}
    late = sum(1 for row in releases if _parse(row["work_end"]) > _parse(row["end_date"]))
    rolled = sum(1 for row in releases if row["close_code"] == "unsuccessful")
    assert late == 3
    assert rolled == 1
    assert all(row["short_description"].startswith("SYN RELEASE ") for row in releases)

    truth = build_ground_truth(fixtures)
    assert truth["patterns"]["p1"]["payments_failure_pct"] == 20.0
    assert truth["patterns"]["p6"]["count"] == 12
    assert truth["metrics"]["release_on_time_pct"] == 85.0
    assert truth["notes"]["caused_by"] == "incident.parent on this PDI"
    assert truth["notes"]["risk_tier_selects_approver"] is False
    assert len(truth["standard_change_candidates"]) == 12


def _parse(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _friday(row: dict) -> bool:
    local = _parse(row["work_start"]).astimezone(EASTERN)
    return local.weekday() == 4 and 15 <= local.hour <= 23


def _fail_pct(rows: list[dict]) -> float:
    return 100 * sum(1 for row in rows if row["close_code"] == "unsuccessful") / len(rows)
