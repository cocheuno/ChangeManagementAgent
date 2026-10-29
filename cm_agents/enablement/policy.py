"""Load config/policy.yaml. Callers do not change the thresholds."""

from __future__ import annotations

from typing import Any

import yaml

from cm_agents.settings import repo_root


def load_policy() -> dict[str, Any]:
    path = repo_root() / "config" / "policy.yaml"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("policy.yaml must be a mapping")
    return loaded
