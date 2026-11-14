"""Config history is append-only, gitignored, and skipped for fixture ids."""

import inspect
import json
from datetime import datetime
from pathlib import Path

from cm_agents.data import config_history
from cm_agents.data.config_history import config_history_path, record_config
from cm_agents.data.load import _ensure_span
from cm_agents.data.teardown import teardown
from cm_agents.settings import repo_root

HEX = "a" * 32
SATURDAY = {
    "name": "SYN Saturday night",
    "start_date_time": "20110101T220000",
    "end_date_time": "20110102T040000",
    "repeat_type": "weekly",
    "days_of_week": "6",
}


class _SpanClient:
    def get_table(self, table: str, **_kwargs: object) -> list[dict[str, str]]:
        return []

    def create_record(self, table: str, body: dict[str, str]) -> dict[str, str]:
        self.stored = dict(body)
        self.stored["sys_id"] = "span1"
        return {"sys_id": "span1"}

    def get_record(self, table: str, sys_id: str, **_kwargs: object) -> dict[str, str]:
        stored = dict(self.stored)
        stored["float_day"] = ""
        stored["float_week"] = ""
        stored["yearly_type"] = ""
        return stored

    def update_record(self, table: str, sys_id: str, body: dict[str, str]) -> dict[str, str]:
        self.stored.update(body)
        return dict(self.stored)


def test_config_history_appends_and_skips_other_rows(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config_history.jsonl"
    monkeypatch.setattr(config_history, "config_history_path", lambda: path)
    moment = datetime(2026, 11, 14, 20, 0, 0, tzinfo=config_history.UTC)
    record_config("create", "cmn_schedule", HEX, "SYN Tier-1", when=moment)
    record_config("delete", "cmn_schedule", HEX, "SYN Tier-1", when=moment)
    record_config("create", "cmn_schedule_span", "span1", "SYN Saturday night", when=moment)
    record_config("create", "incident", HEX, "INC1", when=moment)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    rows = [json.loads(line) for line in lines]
    assert rows[0]["action"] == "create"
    assert rows[1]["action"] == "delete"
    assert rows[0]["table"] == "cmn_schedule"
    assert rows[0]["sys_id"] == HEX
    assert rows[0]["name"] == "SYN Tier-1"
    assert rows[0]["time"] == "2026-11-14 20:00:00"
    record_config("create", "sys_dictionary", HEX, "u_syn_chg_import.u_number", when=moment)
    assert len(path.read_text(encoding="utf-8").splitlines()) == 3


def test_a_span_fixture_id_does_not_create_config_history(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "config_history.jsonl"
    monkeypatch.setattr(config_history, "config_history_path", lambda: path)
    client = _SpanClient()
    manifest: dict[str, object] = {"records": {}}
    _ensure_span(client, manifest, tmp_path / "manifest.json", "sched", SATURDAY)
    assert not path.exists()


def test_config_history_is_gitignored_and_teardown_does_not_delete_it() -> None:
    ignore = (repo_root() / ".gitignore").read_text(encoding="utf-8")
    assert "data/synthetic/" in ignore
    assert config_history_path().name == "config_history.jsonl"
    assert config_history_path().parent == repo_root() / "data" / "synthetic"
    source = inspect.getsource(teardown)
    assert "config_history.jsonl" in source
    for line in source.splitlines():
        if "unlink" in line:
            assert "config_history" not in line
