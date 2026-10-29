"""Append-only JSONL audit log. Values from .env are never written."""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

from cm_agents.data.import_time import UTC
from cm_agents.settings import repo_root


def audit_path():
    return repo_root() / "var" / "audit.jsonl"


def record_audit(
    *,
    thread_id: str,
    agent: str,
    action: str,
    record: str,
    outcome: str,
    model: str = "",
    tokens: int = 0,
    latency_ms: int = 0,
) -> None:
    path = audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    row: dict[str, Any] = {
        "ts": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "thread_id": thread_id,
        "agent": agent,
        "action": action,
        "record": record,
        "outcome": outcome,
        "model": model,
        "tokens": int(tokens),
        "latency_ms": int(latency_ms),
    }
    run = os.environ.get("CM_AGENTS_RUN", "")
    if run:
        row["run"] = run
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def summarize(path=None, *, run: str | None = None) -> dict[str, int]:
    """Count LLM calls and tokens. A call is a row with a model id."""
    target = path or audit_path()
    calls = 0
    tokens = 0
    if not target.is_file():
        return {"calls": 0, "tokens": 0}
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if run is not None and row.get("run") != run:
            continue
        if not row.get("model"):
            continue
        calls += 1
        tokens += int(row.get("tokens") or 0)
    return {"calls": calls, "tokens": tokens}
