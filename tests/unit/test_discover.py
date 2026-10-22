import json

from cm_agents.discover import (
    _compact,
    _password_meta,
    _sys_id,
    _validated_sys_id,
    evaluate_outbound_email,
    probe_role_query,
    residue_queries,
)

_SYS_ID = "a" * 32


def test_email_disabled_and_no_accounts_proceeds() -> None:
    proceed, message = evaluate_outbound_email(
        {"glide.email.smtp.active": "false"},
        active_email_accounts=0,
    )
    assert proceed is True
    assert "SYN-PROBE was not created" not in message


def test_email_enabled_stops_without_extra_values() -> None:
    proceed, message = evaluate_outbound_email(
        {"glide.email.smtp.active": "true"},
        active_email_accounts=0,
    )
    assert proceed is False
    assert "glide.email.smtp.active is true" in message
    assert "SYN-PROBE was not created" in message


def test_missing_smtp_property_stops() -> None:
    proceed, message = evaluate_outbound_email({}, active_email_accounts=0)
    assert proceed is False
    assert "glide.email.smtp.active" in message


def test_unclear_smtp_value_stops_without_echoing_it() -> None:
    proceed, message = evaluate_outbound_email(
        {"glide.email.smtp.active": "maybe-secret"},
        active_email_accounts=0,
    )
    assert proceed is False
    assert "maybe-secret" not in message


def test_active_email_account_stops() -> None:
    proceed, message = evaluate_outbound_email(
        {"glide.email.smtp.active": "false"},
        active_email_accounts=2,
    )
    assert proceed is False
    assert "2 active email accounts" in message


def test_unreadable_email_accounts_stop() -> None:
    proceed, _message = evaluate_outbound_email(
        {"glide.email.smtp.active": "false"},
        active_email_accounts=None,
    )
    assert proceed is False


def test_sys_id_unwraps_display_value_object() -> None:
    payload = {
        "result": {
            "sys_id": {"display_value": _SYS_ID, "value": _SYS_ID},
            "number": {"display_value": "CHG1", "value": "CHG1"},
        }
    }
    assert _sys_id(payload) == _SYS_ID


def test_sys_id_unwraps_json_string_left_by_trimming() -> None:
    trimmed = json.dumps({"display_value": _SYS_ID, "value": _SYS_ID})
    assert _sys_id(trimmed) == _SYS_ID
    assert _sys_id(trimmed) != trimmed


def test_validated_sys_id_uses_the_raw_id() -> None:
    created = {
        "sys_id": _SYS_ID,
        "payload": {"result": {"sys_id": {"value": "b" * 32, "display": "b" * 32}}},
    }
    assert _validated_sys_id(created) == _SYS_ID


def test_compact_keeps_a_usable_sys_id_and_drops_long_text() -> None:
    payload = {
        "result": {
            "sys_id": {"display_value": _SYS_ID, "value": _SYS_ID},
            "description": "x" * 500,
        }
    }
    compact = _compact(payload)
    assert _sys_id(compact) == _SYS_ID
    assert "x" * 500 not in json.dumps(compact)


def test_password_meta_names_no_secret() -> None:
    secret = "Aa1!not-a-real-password"
    meta = _password_meta("hashed-value", secret)
    assert meta["returned_nonempty"] is True
    assert meta["returned_length"] == len("hashed-value")
    assert meta["matches_submitted"] is False
    assert secret not in json.dumps(meta)


def test_role_cleanup_skips_inherited_roles() -> None:
    assert probe_role_query("abc123") == "user=abc123^inherited=false"


def test_residue_queries_cover_probe_children() -> None:
    tables = {table for table, _query in residue_queries()}
    assert {
        "change_request",
        "change_task",
        "task_ci",
        "sysapproval_approver",
        "sysapproval_group",
        "conflict",
    } <= tables
