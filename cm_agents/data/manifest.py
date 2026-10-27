"""Manifest of every synthetic record and import artifact on this instance."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifest is not an object")
    return payload


def save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    """Write the manifest. Retry when OneDrive briefly locks the file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    delay = 0.5
    locked: PermissionError | None = None
    for _ in range(8):
        try:
            path.write_text(payload, encoding="utf-8")
            return
        except PermissionError as exc:
            locked = exc
            time.sleep(delay)
            delay = min(delay * 2, 8.0)
    if locked is not None:
        raise locked


def new_manifest(seed: int, baseline: dict[str, int], anchor: str) -> dict[str, Any]:
    return {
        "seed": seed,
        "anchor": anchor,
        "baseline": baseline,
        "records": {},
        "import_sets": [],
        "staging_tables": [],
        "dictionary": [],
        "transform_maps": [],
        "field_maps": [],
        "update_xml": [],
    }


def add_record(manifest: dict[str, Any], table: str, sys_id: str, key: str) -> None:
    _append(manifest["records"].setdefault(table, []), sys_id, key)


def add_artifact(manifest: dict[str, Any], bucket: str, sys_id: str, key: str) -> None:
    _append(manifest[bucket], sys_id, key)


def _append(rows: list[dict[str, str]], sys_id: str, key: str) -> None:
    if any(row["sys_id"] == sys_id for row in rows):
        return
    rows.append({"sys_id": sys_id, "key": key})
