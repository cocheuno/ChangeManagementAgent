"""Where the change graph goes after scheduling and after each approval step.

A normal change interrupts once per approval step. Authorize approvals do not
exist until the assignment group approves Assess, so one interrupt cannot
cover both steps. See docs/DISCOVERY.md item 5.
"""

from __future__ import annotations


def route_after_schedule(change_type: str) -> str:
    if change_type == "standard":
        return "ready"
    return "risk"


def route_after_authorization(
    *,
    change_type: str,
    pending_step: str | None,
    rejected: bool,
    release_member: bool,
) -> str:
    if rejected:
        return "rejected"
    if pending_step:
        return "authorization"
    if change_type == "emergency":
        return "authorized"
    if release_member:
        return "release_handoff"
    return "go_no_go"


def authority_steps(policy: dict, change_type: str, tier: str) -> list[tuple[str, str]]:
    """Ordered (state step, authority) pairs. Standard has none."""
    if change_type == "standard":
        return []
    if change_type == "emergency":
        authority = policy["change_authority"]["emergency"]["authorize"]
        return [("authorize", authority)]
    block = policy["change_authority"][f"normal_{tier}"]
    return [("assess", block["assess"]), ("authorize", block["authorize"])]


def lead_days(policy: dict, change_type: str, tier: str) -> int:
    table = policy["lead_time_business_days"]
    if change_type == "standard":
        return int(table["standard"])
    if change_type == "emergency":
        return int(table["emergency"])
    return int(table[f"normal_{tier}"])
