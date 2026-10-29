"""One clock for policy decisions. Scenarios may pin it."""

from __future__ import annotations

from datetime import datetime

from cm_agents.data.import_time import UTC

_pinned: datetime | None = None


def now() -> datetime:
    if _pinned is not None:
        return _pinned
    return datetime.now(UTC)


def pin(moment: datetime | None) -> None:
    global _pinned
    _pinned = moment.astimezone(UTC) if moment is not None else None
