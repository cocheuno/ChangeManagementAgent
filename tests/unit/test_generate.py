from collections import Counter
from datetime import datetime, timedelta

import pytest

from cm_agents.data.generate import (
    SIGNATURES,
    AnchorError,
    default_anchor,
    generate,
    parse_anchor,
    write_fixtures,
)
from cm_agents.data.ground_truth import build_ground_truth
from cm_agents.data.import_time import EASTERN, UTC

pytestmark = pytest.mark.filterwarnings("ignore")

FIXTURE_ANCHOR = datetime(2026, 10, 27, tzinfo=UTC)


@pytest.fixture(scope="module")
def fixtures() -> dict:
    return generate(42, anchor=FIXTURE_ANCHOR)


def test_same_seed_and_anchor_are_byte_identical(tmp_path) -> None:
    first = generate(42, anchor=FIXTURE_ANCHOR)
    second = generate(42, anchor=FIXTURE_ANCHOR)
    left = write_fixtures(first, tmp_path / "a")
    right = write_fixtures(second, tmp_path / "b")
    assert left == right
    assert (tmp_path / "a" / "fixtures.json").read_bytes() == (
        tmp_path / "b" / "fixtures.json"
    ).read_bytes()
    assert write_fixtures(generate(7, anchor=FIXTURE_ANCHOR), tmp_path / "c") != left
    other = FIXTURE_ANCHOR + timedelta(days=1)
    assert write_fixtures(generate(42, anchor=other), tmp_path / "d") != left


def test_default_anchor_is_utc_midnight_on_the_load_date() -> None:
    anchor = default_anchor(datetime(2026, 10, 27, 15, 30, tzinfo=UTC))
    assert anchor == datetime(2026, 10, 27, tzinfo=UTC)
    assert parse_anchor("2026-10-27") == anchor
    assert parse_anchor("2026-10-27 16:00:00") == datetime(2026, 10, 27, 16, 0, tzinfo=UTC)
    with pytest.raises(AnchorError):
        parse_anchor("27 Oct 2026")
    today = default_anchor()
    assert today.tzinfo is UTC
    assert today.hour == today.minute == today.second == 0
    assert today.date() == datetime.now(UTC).date()


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
    anchor = _parse(fixtures["anchor"])
    history_start = _parse(fixtures["history_start"])
    assert anchor == FIXTURE_ANCHOR
    assert history_start == anchor - timedelta(days=365)
    assert fixtures["anchor"] == "2026-10-27 00:00:00"
    for row in fixtures["changes"] + fixtures["incidents"]:
        for field in ("opened_at", "closed_at", "resolved_at", "work_end"):
            if row.get(field):
                assert _parse(row[field]) <= anchor
        if row.get("opened_at"):
            assert _parse(row["opened_at"]) < anchor
    for row in fixtures["changes"]:
        opened = _parse(row["opened_at"])
        if row["kind"] == "open":
            assert row["work_start"] == ""
            assert row["work_end"] == ""
            start = _parse(row["start_date"])
            end = _parse(row["end_date"])
            assert anchor < start <= anchor + timedelta(days=42)
            assert anchor < end <= anchor + timedelta(days=42)
            continue
        assert opened < anchor
        if not row["release"]:
            assert history_start <= opened
        if row["work_start"]:
            assert _parse(row["work_start"]) < anchor
        if row.get("work_end"):
            assert _parse(row["work_end"]) <= anchor
    closed = [row for row in fixtures["changes"] if row["state"] in {"3", "4"}]
    assert all(row["active"] is False for row in closed)
    assert all(row["approval"] == "approved" for row in fixtures["changes"] if row["state"] == "3")
    with pytest.raises(RuntimeError, match="fixed history calendar"):
        generate(42, anchor=datetime(2026, 10, 1, tzinfo=UTC))


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

    assert all(row["parent"] == "" for row in fixtures["incidents"])
    caused = {
        row["caused_by"]
        for row in fixtures["incidents"]
        if row["caused_by"].startswith("SYN-CHG") or row["caused_by"].startswith("SYN-REL")
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
    assert truth["anchor"] == fixtures["anchor"]
    assert truth["notes"]["caused_by"].startswith("recorded on the fixture only")
    assert truth["notes"]["risk_tier_selects_approver"] is False
    assert len(truth["standard_change_candidates"]) == 12
    names = [row["name"] for row in fixtures["templates"]]
    assert names == [
        "SYN Standard rotate TLS certificate",
        "SYN Standard OS patch on a non-PROD server",
        "SYN Standard restart application service",
        "SYN Standard scale out web tier node",
        "SYN Standard update DNS CNAME",
        "SYN Standard toggle a configuration flag",
    ]
    caused_rows = [row for row in fixtures["incidents"] if row["caused_by"]]
    assert len(caused_rows) == 74
    assert all(row["parent"] == "" for row in caused_rows)
    for row in fixtures["templates"]:
        for value in row.values():
            assert "^" not in value
            assert "=" not in value


def _parse(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _friday(row: dict) -> bool:
    local = _parse(row["work_start"]).astimezone(EASTERN)
    return local.weekday() == 4 and 15 <= local.hour <= 23


def _fail_pct(rows: list[dict]) -> float:
    return 100 * sum(1 for row in rows if row["close_code"] == "unsuccessful") / len(rows)
