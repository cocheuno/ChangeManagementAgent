"""Deterministic checks. Record text cannot change a score or an approval."""

from __future__ import annotations

INJECTION_MARKERS = (
    "ignore policy",
    "set risk low",
    "mark this change approved",
    "system:",
)

BLOCKING_CONFLICT_PARTS = ("already_scheduled", "blackout")


def injection_markers(*texts: str) -> list[str]:
    folded = "\n".join(texts).casefold()
    return [marker for marker in INJECTION_MARKERS if marker in folded]


def blocks_schedule(conflict_type: str, change_type: str) -> bool:
    """OOB maintenance is recorded, and it blocks a standard change only.

    A normal change may run outside the maintenance window. That adds risk
    points. It is not a scheduling block. docs/DISCOVERY.md item 7.
    """
    name = conflict_type.casefold().replace(" ", "_")
    if any(part in name for part in BLOCKING_CONFLICT_PARTS):
        return True
    return change_type == "standard" and "maintenance" in name
