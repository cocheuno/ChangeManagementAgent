"""Span storage keeps the Eastern wall clock. The schedule zone applies DST."""

from pathlib import Path

import pytest

from cm_agents.data.load import SeedError, _ensure_span, _span_matches, schedule_span_clock


def test_saturday_night_is_stored_as_the_eastern_wall_clock() -> None:
    assert schedule_span_clock("20110101T220000") == "20110101T220000"
    assert schedule_span_clock("20110102T040000") == "20110102T040000"


def test_tuesday_and_thursday_evenings_are_stored_as_the_eastern_wall_clock() -> None:
    assert schedule_span_clock("20110104T200000") == "20110104T200000"
    assert schedule_span_clock("20110104T230000") == "20110104T230000"
    assert schedule_span_clock("20110106T200000") == "20110106T200000"
    assert schedule_span_clock("20110106T230000") == "20110106T230000"


def test_a_summer_clock_is_not_rewritten_to_utc() -> None:
    assert schedule_span_clock("20110605T220000") == "20110605T220000"
    assert schedule_span_clock("20110606T040000") == "20110606T040000"


def test_a_span_clock_must_be_compact() -> None:
    with pytest.raises(ValueError):
        schedule_span_clock("2011-01-01 22:00:00")


SATURDAY = {
    "name": "SYN Saturday night",
    "start_date_time": "20110101T220000",
    "end_date_time": "20110102T040000",
    "repeat_type": "weekly",
    "days_of_week": "6",
}


def _body() -> dict[str, str]:
    return {
        "name": "SYN Saturday night",
        "schedule": "sched",
        "start_date_time": "20110101T220000",
        "end_date_time": "20110102T040000",
        "repeat_type": "weekly",
        "repeat_count": "1",
        "days_of_week": "6",
        "all_day": "false",
        "float_day": "",
        "float_week": "",
        "yearly_type": "",
    }


def test_dictionary_defaults_do_not_match_the_out_of_box_span() -> None:
    stored = _body()
    stored["float_day"] = "1"
    stored["float_week"] = "1"
    stored["yearly_type"] = "doy"
    assert _span_matches(stored, _body()) is False
    assert _span_matches(_body(), _body()) is True


def test_a_rewritten_clock_does_not_match() -> None:
    stored = _body()
    stored["start_date_time"] = "20110102T030000"
    assert _span_matches(stored, _body()) is False


class _SpanClient:
    def __init__(self, *, existing: dict[str, str] | None = None, stick: bool = True) -> None:
        self.existing = existing
        self.stick = stick
        self.updates: list[dict[str, str]] = []
        self.stored: dict[str, str] = {}

    def get_table(self, table: str, **_kwargs: object) -> list[dict[str, str]]:
        if self.existing is None:
            return []
        return [dict(self.existing)]

    def create_record(self, table: str, body: dict[str, str]) -> dict[str, str]:
        self.stored = dict(body)
        self.stored["sys_id"] = "span1"
        self.stored["float_day"] = "1"
        self.stored["float_week"] = "1"
        self.stored["yearly_type"] = "doy"
        return {"sys_id": "span1"}

    def get_record(self, table: str, sys_id: str, **_kwargs: object) -> dict[str, str]:
        return dict(self.stored)

    def update_record(self, table: str, sys_id: str, body: dict[str, str]) -> dict[str, str]:
        self.updates.append(dict(body))
        if self.stick:
            self.stored.update(body)
        return dict(self.stored)


def test_a_new_span_clears_dictionary_defaults_with_an_update(tmp_path: Path) -> None:
    client = _SpanClient()
    manifest: dict[str, object] = {"records": {}}
    _ensure_span(client, manifest, tmp_path / "manifest.json", "sched", SATURDAY)
    assert client.updates
    assert client.stored["start_date_time"] == "20110101T220000"
    assert client.stored["end_date_time"] == "20110102T040000"
    assert client.stored["float_day"] == ""
    assert client.stored["yearly_type"] == ""
    recorded = manifest["records"]["cmn_schedule_span"]
    assert recorded == [{"sys_id": "span1", "key": "SYN Saturday night"}]


def test_an_existing_matching_span_is_recorded_without_an_update(tmp_path: Path) -> None:
    existing = _body()
    existing["sys_id"] = "span9"
    client = _SpanClient(existing=existing)
    manifest: dict[str, object] = {"records": {}}
    _ensure_span(client, manifest, tmp_path / "manifest.json", "sched", SATURDAY)
    assert client.updates == []
    assert manifest["records"]["cmn_schedule_span"][0]["sys_id"] == "span9"


def test_a_clock_the_platform_rewrites_still_fails(tmp_path: Path) -> None:
    class Rewritten(_SpanClient):
        def update_record(self, table: str, sys_id: str, body: dict[str, str]) -> dict[str, str]:
            self.updates.append(dict(body))
            self.stored.update(body)
            self.stored["start_date_time"] = "20110102T030000"
            return dict(self.stored)

    client = Rewritten()
    manifest: dict[str, object] = {"records": {}}
    with pytest.raises(SeedError, match="start_date_time"):
        _ensure_span(client, manifest, tmp_path / "manifest.json", "sched", SATURDAY)
