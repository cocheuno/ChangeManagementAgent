"""Record and restore the two approved out-of-box values. No network."""

import inspect

from cm_agents.data.load import _ensure_conflict_uses_ci_schedule
from cm_agents.data.manifest import load_manifest, new_manifest, save_manifest
from cm_agents.data.oob import (
    GLOBAL_CONDITION_KEY,
    PROPERTY_KEY,
    record_oob_original,
    restore_oob_originals,
)
from cm_agents.data.teardown import teardown


class _Instance:
    def __init__(self, property_value: str, condition: str) -> None:
        self.property = {"sys_id": "prop1", "value": property_value}
        self.schedule = {"sys_id": "sched1", "condition": condition}
        self.updates: list[tuple[str, str, dict[str, str]]] = []

    def get_table(self, table: str, **_kwargs: object) -> list[dict[str, str]]:
        if table == "sys_properties":
            return [dict(self.property)]
        if table == "cmn_schedule_maintenance":
            return [dict(self.schedule)]
        return []

    def update_record(self, table: str, sys_id: str, fields: dict[str, str]) -> dict[str, str]:
        self.updates.append((table, sys_id, dict(fields)))
        if table == "sys_properties":
            self.property["value"] = fields["value"]
        if table == "cmn_schedule_maintenance":
            self.schedule["condition"] = fields["condition"]
        return {}

    def get_record(self, table: str, sys_id: str, **_kwargs: object) -> dict[str, str]:
        if table == "sys_properties":
            return {"value": self.property["value"]}
        return {"condition": self.schedule["condition"]}


def test_seed_records_the_value_read_before_it_writes(tmp_path) -> None:
    path = tmp_path / "manifest.json"
    manifest = new_manifest(42, {}, "2026-10-27 00:00:00")
    save_manifest(path, manifest)
    client = _Instance("false", "")
    _ensure_conflict_uses_ci_schedule(client, manifest, path)
    stored = load_manifest(path)
    assert stored is not None
    assert stored["oob_originals"][PROPERTY_KEY]["value"] == "false"
    assert stored["oob_originals"][GLOBAL_CONDITION_KEY]["value"] == ""
    assert client.property["value"] == "true"
    assert client.schedule["condition"] == "nameNOT LIKEsyn-"
    assert client.updates[0] == ("sys_properties", "prop1", {"value": "true"})
    assert client.updates[1][2] == {"condition": "nameNOT LIKEsyn-"}


def test_seed_does_not_replace_a_stored_original(tmp_path) -> None:
    path = tmp_path / "manifest.json"
    manifest = new_manifest(42, {}, "2026-10-27 00:00:00")
    record_oob_original(
        manifest,
        PROPERTY_KEY,
        table="sys_properties",
        sys_id="prop1",
        field="value",
        value="false",
    )
    record_oob_original(
        manifest,
        GLOBAL_CONDITION_KEY,
        table="cmn_schedule_maintenance",
        sys_id="sched1",
        field="condition",
        value="",
    )
    save_manifest(path, manifest)
    client = _Instance("true", "nameNOT LIKEsyn-")
    _ensure_conflict_uses_ci_schedule(client, manifest, path)
    stored = load_manifest(path)
    assert stored is not None
    assert stored["oob_originals"][PROPERTY_KEY]["value"] == "false"
    assert stored["oob_originals"][GLOBAL_CONDITION_KEY]["value"] == ""
    assert client.updates == []


def test_restore_writes_the_stored_originals_back() -> None:
    class _Store:
        def __init__(self) -> None:
            self.rows = {
                ("sys_properties", "prop1"): {"value": "true"},
                ("cmn_schedule_maintenance", "sched1"): {"condition": "nameNOT LIKEsyn-"},
            }

        def update_record(self, table: str, sys_id: str, fields: dict[str, str]) -> dict[str, str]:
            self.rows[(table, sys_id)].update(fields)
            return dict(self.rows[(table, sys_id)])

        def get_record(self, table: str, sys_id: str, **_kwargs: object) -> dict[str, str]:
            return dict(self.rows[(table, sys_id)])

    client = _Store()
    manifest = {
        "oob_originals": {
            PROPERTY_KEY: {
                "table": "sys_properties",
                "sys_id": "prop1",
                "field": "value",
                "value": "false",
            },
            GLOBAL_CONDITION_KEY: {
                "table": "cmn_schedule_maintenance",
                "sys_id": "sched1",
                "field": "condition",
                "value": "",
            },
        }
    }
    restore_oob_originals(client, manifest)
    assert client.rows[("sys_properties", "prop1")]["value"] == "false"
    assert client.rows[("cmn_schedule_maintenance", "sched1")]["condition"] == ""


def test_teardown_restores_originals_after_the_data_rows() -> None:
    source = inspect.getsource(teardown)
    delete_at = source.index("_delete_recorded")
    restore_at = source.index("restore_oob_originals")
    unlink_at = source.index("path.unlink")
    assert delete_at < restore_at < unlink_at
