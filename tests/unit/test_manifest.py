import json
import os
from pathlib import Path

import pytest

from cm_agents.data.manifest import save_manifest


def test_save_manifest_replaces_a_temp_file_in_the_same_folder(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    save_manifest(path, {"seed": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"seed": 1}
    assert list(tmp_path.glob("*.tmp")) == []


def test_save_manifest_retries_a_sharing_violation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "manifest.json"
    path.write_text('{"seed": 1}\n', encoding="utf-8")
    calls = {"replace": 0}
    real_replace = os.replace

    def flaky(source: str, destination: str) -> None:
        calls["replace"] += 1
        if calls["replace"] == 1:
            raise PermissionError(13, "sharing violation", destination)
        real_replace(source, destination)

    monkeypatch.setattr("cm_agents.data.manifest.os.replace", flaky)
    monkeypatch.setattr("cm_agents.data.manifest.time.sleep", lambda _delay: None)
    save_manifest(path, {"seed": 2})
    assert json.loads(path.read_text(encoding="utf-8")) == {"seed": 2}
    assert calls["replace"] == 2
    assert list(tmp_path.glob("*.tmp")) == []


def test_save_manifest_keeps_the_original_when_the_lock_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "manifest.json"
    original = '{"seed": 1}\n'
    path.write_text(original, encoding="utf-8")

    def locked(_source: str, destination: str) -> None:
        raise PermissionError(13, "sharing violation", destination)

    monkeypatch.setattr("cm_agents.data.manifest.os.replace", locked)
    monkeypatch.setattr("cm_agents.data.manifest.time.sleep", lambda _delay: None)
    with pytest.raises(PermissionError):
        save_manifest(path, {"anchor": "2026-10-27 00:00:00", "seed": 2})
    assert path.read_text(encoding="utf-8") == original
    written = json.loads((tmp_path / "manifest.json.tmp").read_text(encoding="utf-8"))
    assert written["seed"] == 2
    assert written["anchor"] == "2026-10-27 00:00:00"
