"""Table API batch helper. A rejected batch call falls back to one row at a time."""

from __future__ import annotations

import json
from typing import Any

from cm_agents.servicenow.client import ServiceNowClient, ServiceNowError

_HEADERS = [
    {"name": "Accept", "value": "application/json"},
    {"name": "Content-Type", "value": "application/json"},
]


class BatchError(Exception):
    """One request inside a batch was rejected."""


def batch_create(client: ServiceNowClient, table: str, bodies: list[dict[str, Any]]) -> list[str]:
    if not bodies:
        return []
    try:
        payload = client.request(
            "POST", "/api/now/v1/batch", json=_envelope(_creates(table, bodies))
        )
    except ServiceNowError:
        return [str(client.create_record(table, body)["sys_id"]) for body in bodies]
    return _created_ids(payload, len(bodies))


def batch_delete(client: ServiceNowClient, table: str, sys_ids: list[str]) -> None:
    if not sys_ids:
        return
    try:
        payload = client.request(
            "POST", "/api/now/v1/batch", json=_envelope(_deletes(table, sys_ids))
        )
    except ServiceNowError:
        for sys_id in sys_ids:
            _delete_one(client, table, sys_id)
        return
    for item in _serviced(payload):
        status = _status(item)
        if status >= 400 and status != 404:
            raise BatchError(f"batch delete {table} returned HTTP {status}")


def _creates(table: str, bodies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for index, body in enumerate(bodies):
        item = _item(index, "POST", f"/api/now/table/{table}?sysparm_exclude_reference_link=true")
        item["body"] = json.dumps(body)
        items.append(item)
    return items


def _deletes(table: str, sys_ids: list[str]) -> list[dict[str, Any]]:
    return [
        _item(index, "DELETE", f"/api/now/table/{table}/{sys_id}")
        for index, sys_id in enumerate(sys_ids)
    ]


def _item(index: int, method: str, url: str) -> dict[str, Any]:
    return {
        "id": str(index),
        "exclude_response_headers": True,
        "headers": _HEADERS,
        "url": url,
        "method": method,
    }


def _envelope(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"batch_request_id": "syn", "rest_requests": items}


def _created_ids(payload: dict[str, Any], expected: int) -> list[str]:
    serviced = _serviced(payload)
    by_id = {str(item.get("id")): item for item in serviced}
    ids: list[str] = []
    for index in range(expected):
        item = by_id.get(str(index))
        if item is None:
            raise BatchError("batch response missed a request")
        status = _status(item)
        if status >= 400:
            raise BatchError(f"batch create returned HTTP {status}")
        body = _body(item)
        result = body.get("result") if isinstance(body, dict) else None
        sys_id = result.get("sys_id") if isinstance(result, dict) else None
        if not sys_id:
            raise BatchError("batch create did not return a sys_id")
        ids.append(str(sys_id))
    return ids


def _serviced(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("serviced_requests")
    if not isinstance(rows, list):
        raise BatchError("batch response did not list serviced requests")
    return [row for row in rows if isinstance(row, dict)]


def _body(item: dict[str, Any]) -> dict[str, Any]:
    body = item.get("body")
    if isinstance(body, dict):
        return body
    if isinstance(body, str) and body:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _status(item: dict[str, Any]) -> int:
    try:
        return int(item.get("status_code") or 0)
    except (TypeError, ValueError):
        return 0


def _delete_one(client: ServiceNowClient, table: str, sys_id: str) -> None:
    try:
        client.delete_record(table, sys_id)
    except ServiceNowError as exc:
        if exc.status_code != 404:
            raise
