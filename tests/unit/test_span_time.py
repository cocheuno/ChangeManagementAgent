"""Span storage keeps the Eastern wall clock. The schedule zone applies DST."""

import pytest

from cm_agents.data.load import schedule_span_clock


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
