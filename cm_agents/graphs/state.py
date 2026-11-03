"""Checkpointed change state. Values stay JSON-serializable."""

from __future__ import annotations

from typing import Any, TypedDict


class ChangeState(TypedDict, total=False):
    thread_id: str
    request: dict[str, Any]
    change_sys_id: str
    change_number: str
    change_type: str
    service: str
    service_tier: int
    assignment_group: str
    affected_cis: list[dict[str, str]]
    impacted_service_names: list[str]
    gaps: list[str]
    injection: list[str]
    release_member: bool
    error: str
    checklist: dict[str, bool]
    schedule: dict[str, Any]
    risk: dict[str, Any]
    authorization: dict[str, Any]
    service_link: str
    deployment: dict[str, Any]
    review: dict[str, Any]


class ReleaseState(TypedDict, total=False):
    """One release thread. The release itself is a normal change."""

    thread_id: str
    request: dict[str, Any]
    change_sys_id: str
    change_number: str
    change_type: str
    service: str
    service_tier: int
    version: str
    assignment_group: str
    impacted_service_names: list[str]
    release_member: bool
    error: str
    schedule: dict[str, Any]
    risk: dict[str, Any]
    authorization: dict[str, Any]
    readiness: dict[str, Any]
    member_checks: dict[str, dict[str, bool]]
    deployment: dict[str, Any]
    review: dict[str, Any]
