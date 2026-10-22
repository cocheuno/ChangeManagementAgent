"""ServiceNow Table API client for a Personal Developer Instance.

Hibernation returns HTML instead of JSON and fails immediately. HTTP 429 and 5xx
are retried up to three times. Secrets are removed from logs and error text.
"""

from __future__ import annotations

import base64
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from cm_agents.settings import assert_pdi_url, redact_text

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 60.0


def backoff_seconds(attempt: int) -> float:
    """Delay before the next try. `attempt` is the number of failures so far, starting at 0."""
    return 0.5 * (2**attempt)


class ServiceNowError(Exception):
    """The instance returned an error, or the request could not be completed."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PdiAsleepError(ServiceNowError):
    """The instance returned a non-JSON response. Wake the PDI and run the command again."""


class ServiceNowClient:
    def __init__(
        self,
        base_url: str,
        user: str,
        password: str,
        *,
        secrets: list[str] | None = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        assert_pdi_url(base_url)
        self.base_url = base_url
        self._max_retries = max_retries
        self._sleep = sleep
        token = base64.b64encode(f"{user}:{password}".encode()).decode("ascii")
        self._secrets = [value for value in (secrets or []) if value]
        self._secrets.extend([password, token, f"Basic {token}"])
        self._http = httpx.Client(
            base_url=base_url,
            auth=httpx.BasicAuth(user, password),
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> ServiceNowClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        last_response: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._http.request(method, path, params=params, json=json)
            except httpx.HTTPError:
                logger.error("%s %s failed before a response", method, path)
                raise ServiceNowError(f"{method} {path} failed before a response") from None
            last_response = response
            if _retryable(response.status_code) and attempt < self._max_retries:
                delay = backoff_seconds(attempt)
                logger.info(
                    "%s %s -> HTTP %s; retrying in %s seconds",
                    method,
                    path,
                    response.status_code,
                    delay,
                )
                self._sleep(delay)
                continue
            logger.info("%s %s -> HTTP %s", method, path, response.status_code)
            return self._interpret(response)
        # Unreachable: the loop returns or retries. Kept so a future edit can't fall through.
        if last_response is not None:
            return self._interpret(last_response)
        raise ServiceNowError(f"{method} {path} failed before a response")

    def get_table(
        self,
        table: str,
        *,
        query: str | None = None,
        fields: list[str] | None = None,
        limit: int = 100,
        offset: int = 0,
        display_value: bool = False,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "sysparm_display_value": "true" if display_value else "false",
            "sysparm_exclude_reference_link": "true",
            "sysparm_limit": str(limit),
            "sysparm_offset": str(offset),
        }
        if query:
            params["sysparm_query"] = query
        if fields:
            params["sysparm_fields"] = ",".join(fields)
        payload = self.request("GET", f"/api/now/table/{table}", params=params)
        return _result_records(payload)

    def get_records(
        self,
        table: str,
        *,
        query: str | None = None,
        fields: list[str] | None = None,
        page_size: int = 200,
        display_value: bool = False,
        max_records: int = 2000,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        offset = 0
        while len(rows) < max_records:
            page = self.get_table(
                table,
                query=query,
                fields=fields,
                limit=page_size,
                offset=offset,
                display_value=display_value,
            )
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
        return rows[:max_records]

    def get_record(
        self,
        table: str,
        sys_id: str,
        *,
        fields: list[str] | None = None,
    ) -> dict[str, Any]:
        params: dict[str, str] = {
            "sysparm_display_value": "false",
            "sysparm_exclude_reference_link": "true",
        }
        if fields:
            params["sysparm_fields"] = ",".join(fields)
        payload = self.request("GET", f"/api/now/table/{table}/{sys_id}", params=params)
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ServiceNowError(f"Record {table} was not found")
        return result

    def create_record(self, table: str, fields: dict[str, Any]) -> dict[str, Any]:
        payload = self.request(
            "POST",
            f"/api/now/table/{table}",
            params={"sysparm_display_value": "false", "sysparm_exclude_reference_link": "true"},
            json=fields,
        )
        result = payload.get("result")
        if not isinstance(result, dict) or not result.get("sys_id"):
            raise ServiceNowError(f"Create on {table} did not return a record")
        return result

    def update_record(self, table: str, sys_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        payload = self.request(
            "PATCH",
            f"/api/now/table/{table}/{sys_id}",
            params={"sysparm_display_value": "false", "sysparm_exclude_reference_link": "true"},
            json=fields,
        )
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ServiceNowError(f"Update on {table} did not return a record")
        return result

    def delete_record(self, table: str, sys_id: str) -> None:
        self.request("DELETE", f"/api/now/table/{table}/{sys_id}")

    def _interpret(self, response: httpx.Response) -> dict[str, Any]:
        if 300 <= response.status_code < 400:
            raise PdiAsleepError(
                "ServiceNow returned a redirect instead of JSON. wake your PDI and try again."
            )
        parsed = _parse_body(response)
        if parsed is None:
            raise PdiAsleepError(
                "ServiceNow returned a non-JSON response. wake your PDI and try again."
            )
        if response.status_code >= 400:
            raise ServiceNowError(
                self._error_message(response.status_code, parsed),
                response.status_code,
            )
        return parsed

    def _error_message(self, status_code: int, payload: dict[str, Any]) -> str:
        error = payload.get("error")
        detail = ""
        if isinstance(error, dict):
            message = str(error.get("message") or "")
            extra = str(error.get("detail") or "")
            detail = " ".join(part for part in (message, extra) if part)
        elif error:
            detail = str(error)
        text = f"ServiceNow returned HTTP {status_code}"
        if detail:
            text = f"{text}: {detail}"
        return redact_text(text, self._secrets)


def _retryable(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


def _parse_body(response: httpx.Response) -> dict[str, Any] | None:
    if response.status_code == 204 or not response.content:
        if 200 <= response.status_code < 300:
            return {}
        return {"error": {"message": "empty error response"}}
    content_type = response.headers.get("content-type", "")
    if "html" in content_type.lower():
        return None
    try:
        data = response.json()
    except ValueError:
        return None
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {"result": data}
    return None


def _result_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    if isinstance(result, list):
        return [row for row in result if isinstance(row, dict)]
    if isinstance(result, dict):
        return [result]
    return []
