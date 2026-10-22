import logging

import httpx
import pytest
import respx

from cm_agents.cli import RedactFilter
from cm_agents.servicenow.client import (
    PdiAsleepError,
    ServiceNowClient,
    ServiceNowError,
    backoff_seconds,
)
from cm_agents.settings import SettingsError

BASE = "https://dev123.service-now.com"
PASSWORD = "pw-value"


def _client(sleep=None) -> ServiceNowClient:
    return ServiceNowClient(
        BASE,
        "admin",
        PASSWORD,
        secrets=["xai-secret"],
        sleep=sleep or (lambda _seconds: None),
    )


@respx.mock
def test_html_hibernation_page_raises_and_does_not_retry() -> None:
    route = respx.get(url__regex=r".*/api/now/table/sys_user").mock(
        return_value=httpx.Response(
            200,
            text="<html><body>Instance Hibernating</body></html>",
            headers={"content-type": "text/html; charset=utf-8"},
        )
    )
    with pytest.raises(PdiAsleepError, match="wake your PDI"):
        _client().get_table("sys_user", limit=1)
    assert route.call_count == 1


@respx.mock
def test_redirect_is_treated_as_hibernation_and_not_followed() -> None:
    route = respx.get(url__regex=r".*/api/now/table/sys_user").mock(
        return_value=httpx.Response(302, headers={"location": "https://example.test/wake"})
    )
    with pytest.raises(PdiAsleepError, match="wake your PDI"):
        _client().get_table("sys_user", limit=1)
    assert route.call_count == 1


@respx.mock
def test_retries_429_three_times_then_succeeds() -> None:
    delays: list[float] = []
    route = respx.get(url__regex=r".*/api/now/table/sys_user").mock(
        side_effect=[
            httpx.Response(429, json={"error": {"message": "too many"}}),
            httpx.Response(429, json={"error": {"message": "too many"}}),
            httpx.Response(429, json={"error": {"message": "too many"}}),
            httpx.Response(200, json={"result": [{"sys_id": "abc"}]}),
        ]
    )
    rows = _client(sleep=delays.append).get_table("sys_user", limit=1)
    assert rows == [{"sys_id": "abc"}]
    assert route.call_count == 4
    assert delays == [backoff_seconds(0), backoff_seconds(1), backoff_seconds(2)]


@respx.mock
def test_retries_5xx_then_succeeds() -> None:
    delays: list[float] = []
    route = respx.get(url__regex=r".*/api/now/table/sys_user").mock(
        side_effect=[
            httpx.Response(503, json={"error": {"message": "down"}}),
            httpx.Response(200, json={"result": []}),
        ]
    )
    assert _client(sleep=delays.append).get_table("sys_user") == []
    assert route.call_count == 2
    assert delays == [0.5]


@respx.mock
def test_exhausted_429_raises_after_three_retries() -> None:
    delays: list[float] = []
    route = respx.get(url__regex=r".*/api/now/table/sys_user").mock(
        side_effect=[
            httpx.Response(429, json={"error": {"message": "too many"}}) for _ in range(4)
        ]
    )
    with pytest.raises(ServiceNowError) as exc:
        _client(sleep=delays.append).get_table("sys_user")
    assert exc.value.status_code == 429
    assert route.call_count == 4
    assert delays == [0.5, 1.0, 2.0]


@respx.mock
def test_client_error_is_not_retried() -> None:
    delays: list[float] = []
    route = respx.get(url__regex=r".*/api/now/table/sys_user").mock(
        return_value=httpx.Response(400, json={"error": {"message": "bad query"}})
    )
    with pytest.raises(ServiceNowError) as exc:
        _client(sleep=delays.append).get_table("sys_user")
    assert exc.value.status_code == 400
    assert "bad query" in str(exc.value)
    assert route.call_count == 1
    assert delays == []


@respx.mock
def test_error_text_redacts_secrets() -> None:
    respx.get(url__regex=r".*/api/now/table/sys_user").mock(
        return_value=httpx.Response(
            400,
            json={"error": {"message": "rejected", "detail": f"saw {PASSWORD} and xai-secret"}},
        )
    )
    with pytest.raises(ServiceNowError) as exc:
        _client().get_table("sys_user")
    message = str(exc.value)
    assert PASSWORD not in message
    assert "xai-secret" not in message
    assert "***" in message


@respx.mock
def test_empty_204_delete_is_success() -> None:
    route = respx.delete(url__regex=r".*/api/now/table/change_request/abc").mock(
        return_value=httpx.Response(204)
    )
    _client().delete_record("change_request", "abc")
    assert route.call_count == 1


@respx.mock
def test_request_log_does_not_include_the_password(caplog: pytest.LogCaptureFixture) -> None:
    respx.get(url__regex=r".*/api/now/table/sys_user").mock(
        return_value=httpx.Response(200, json={"result": []})
    )
    with caplog.at_level(logging.INFO):
        _client().get_table("sys_user")
    assert PASSWORD not in caplog.text
    assert "xai-secret" not in caplog.text


def test_client_rejects_non_pdi_url_without_echoing_it() -> None:
    url = "https://example.service-now.com"
    with pytest.raises(SettingsError) as exc:
        ServiceNowClient(url, "admin", PASSWORD)
    message = str(exc.value)
    assert "SN_INSTANCE_URL" in message
    assert url not in message
    assert PASSWORD not in message


def test_redact_filter_removes_secret_from_log_records() -> None:
    record = logging.LogRecord(
        name="cm_agents",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="token %s",
        args=(PASSWORD,),
        exc_info=None,
    )
    assert RedactFilter([PASSWORD]).filter(record) is True
    assert record.getMessage() == "token ***"
    assert PASSWORD not in record.getMessage()
