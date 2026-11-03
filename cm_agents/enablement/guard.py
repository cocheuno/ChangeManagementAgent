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
    """CI overlap and blackout block every type. The OOB maintenance flag does not.

    Policy code decides whether a window is inside maintenance. On this PDI the
    stored span is a UTC clock time, so ServiceNow flags the policy Saturday
    window. A normal change may also run outside that window; that adds risk
    points. docs/DISCOVERY.md Phase 3.
    """
    name = conflict_type.casefold().replace(" ", "_")
    return any(part in name for part in BLOCKING_CONFLICT_PARTS)
