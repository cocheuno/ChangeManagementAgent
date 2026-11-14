"""sys_update_xml classification. No network."""

import pytest

from cm_agents.data.update_xml import (
    UpdateXmlError,
    classify_row,
    classify_text,
    manifest_ids,
    update_xml_query,
)

KNOWN = {"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}
PROPERTY = "638460b6b70023008ef6eac7ee11a9f2"


def test_query_keeps_the_user_test_on_both_dates() -> None:
    query = update_xml_query(["alice", "bob"], "2026-10-20 00:00:00")
    assert query == (
        "sys_created_byINalice,bob^sys_created_on>=2026-10-20 00:00:00"
        "^NQsys_created_byINalice,bob^sys_updated_on>=2026-10-20 00:00:00"
    )
    with pytest.raises(UpdateXmlError):
        update_xml_query(["alice^admin"])


def test_manifest_ids_include_records_and_the_approved_originals() -> None:
    found = manifest_ids(
        {
            "records": {"change_request": [{"sys_id": "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"}]},
            "dictionary": [{"sys_id": "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC", "key": "col"}],
            "oob_originals": {
                "change.conflict.ci_maint_sched": {
                    "table": "sys_properties",
                    "sys_id": PROPERTY,
                    "field": "value",
                    "value": "false",
                }
            },
        }
    )
    assert "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb" in found
    assert "cccccccccccccccccccccccccccccccc" in found
    assert PROPERTY in found


def test_a_row_maps_to_manifest_approved_or_hand_made() -> None:
    assert classify_text(f"change_request_{next(iter(KNOWN))}", KNOWN) == (
        "manifest",
        next(iter(KNOWN)),
    )
    assert classify_text(f"sys_properties_{PROPERTY}", KNOWN)[0] == "approved"
    assert classify_text("sys_dictionary_incident_u_caused_by", KNOWN) == (
        "hand_made",
        "incident.u_caused_by field (setup guide Part B8)",
    )
    assert classify_text("sys_dictionary_u_syn_inc_import_u_u_caused_by", KNOWN) is None
    role = {
        "name": "sys_user_has_role_dddddddddddddddddddddddddddddddd",
        "target_name": "sys_user_has_role",
    }
    assert classify_row(role, KNOWN)[0] == "orphan"
    kind, detail = classify_row(role, KNOWN, "<role>snc_basic_auth_api_access</role>")
    assert kind == "hand_made"
    assert "Part B5" in detail
    payload = f"<sys_id>{next(iter(KNOWN))}</sys_id> u_caused_by"
    row = {"name": "sys_transform_map_x", "target_name": "sys_transform_map"}
    assert classify_row(row, KNOWN, payload)[0] == "manifest"


def test_an_unknown_row_stays_an_orphan() -> None:
    kind, detail = classify_row(
        {"name": "sys_ui_policy_eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee", "target_name": "sys_ui_policy"},
        KNOWN,
        "<name>Some other policy</name>",
    )
    assert kind == "orphan"
    assert detail == ""
