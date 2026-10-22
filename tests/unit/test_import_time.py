from datetime import datetime

from cm_agents.data.import_time import UTC, format_utc, to_import_wall


def test_import_wall_time_follows_pacific_dst() -> None:
    assert to_import_wall("2025-06-01 14:00:00") == "2025-06-01 07:00:00"
    assert to_import_wall("2025-01-15 14:00:00") == "2025-01-15 06:00:00"


def test_fallback_hour_uses_the_instant_the_import_api_stores() -> None:
    pdt = datetime(2025, 11, 2, 8, 0, tzinfo=UTC)
    pst = datetime(2025, 11, 2, 9, 0, tzinfo=UTC)
    assert format_utc(pdt) == "2025-11-02 09:00:00"
    assert format_utc(pst) == "2025-11-02 09:00:00"
    assert to_import_wall("2025-11-02 09:00:00") == "2025-11-02 01:00:00"
    assert format_utc(datetime(2025, 6, 1, 14, 0, tzinfo=UTC)) == "2025-06-01 14:00:00"
