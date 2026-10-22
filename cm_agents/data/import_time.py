"""Convert UTC timestamps into the wall time the Import Set API expects.

On this instance the Import Set API reads a date-time string as America/Los_Angeles
and stores UTC. June 2025 shifts by 7 hours and January 2025 shifts by 8.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

UTC = ZoneInfo("UTC")
PACIFIC = ZoneInfo("America/Los_Angeles")
EASTERN = ZoneInfo("America/New_York")

_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_utc(text: str) -> datetime:
    return datetime.strptime(text, _FORMAT).replace(tzinfo=UTC)


def storable_utc(moment: datetime) -> datetime:
    """Move the repeated Pacific hour onto the instant this instance stores.

    On the fall-back Sunday, 01:00 America/Los_Angeles happens twice. The Import
    Set API stores that wall time as PST, one hour later than the PDT instant.
    """
    utc = moment.astimezone(UTC)
    wall = utc.astimezone(PACIFIC)
    earlier = wall.replace(fold=0).astimezone(UTC)
    later = wall.replace(fold=1).astimezone(UTC)
    if earlier != later and utc == earlier:
        return later
    return utc


def format_utc(moment: datetime) -> str:
    return storable_utc(moment).strftime(_FORMAT)


def to_import_wall(utc_text: str) -> str:
    """Return the Pacific wall time that the import API will store as `utc_text`."""
    return parse_utc(utc_text).astimezone(PACIFIC).strftime(_FORMAT)
