"""Seeded deployment simulator. Failures happen only when a scenario injects one."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cm_agents.settings import repo_root

HEALTHY = {"error_rate_pct": 0.4, "p95_latency_ms": 120.0, "availability_pct": 99.9}
FAILED = {"error_rate_pct": 8.0, "p95_latency_ms": 400.0, "availability_pct": 97.0}
STRATEGIES = {
    "canary": ("canary_10", "canary_100"),
    "blue/green": ("switch",),
    "blue_green": ("switch",),
    "rolling": ("batch_25", "batch_50", "batch_75", "batch_100"),
    "big bang": ("all",),
    "big_bang": ("all",),
}


class SimulatorError(RuntimeError):
    """The strategy is unknown, or the state file cannot be used."""


class RedeployBlocked(SimulatorError):
    """A later PROD deploy is refused after a recorded failure."""


def default_path() -> Path:
    return repo_root() / "var" / "sim_state.json"


def steps_for(strategy: str) -> tuple[str, ...]:
    key = (strategy or "big bang").strip().lower()
    found = STRATEGIES.get(key)
    if found is None:
        raise SimulatorError(f"unknown deployment strategy {strategy}")
    return found


def passes_thresholds(
    before: dict[str, float], after: dict[str, float], policy: dict[str, Any]
) -> bool:
    limits = policy["verification"]
    if float(after["error_rate_pct"]) > float(limits["error_rate_max_pct"]):
        return False
    if float(after["availability_pct"]) < float(limits["availability_min_pct"]):
        return False
    base = float(before["p95_latency_ms"]) or 1.0
    increase = (float(after["p95_latency_ms"]) - base) / base * 100.0
    return increase <= float(limits["p95_latency_max_increase_pct"])


def run_deploy(
    path: Path,
    *,
    thread_id: str,
    ci: str,
    environment: str,
    strategy: str,
    version: str,
    fail_at: dict[str, Any] | None,
) -> dict[str, Any]:
    """Deploy one version. A replay of the same thread does not run the steps again."""
    state = _load(path)
    existing = (state.get("threads") or {}).get(thread_id)
    if isinstance(existing, dict) and existing.get("kind") == "deploy":
        replay = dict(existing)
        replay["replayed"] = True
        return replay
    env = environment.upper()
    failed = list(state.get("failed_prod") or [])
    if env == "PROD" and ci in failed:
        raise RedeployBlocked(f"PROD deploy blocked for {ci} after a recorded failure")
    key = f"{ci}|{env}"
    versions = dict(state.get("versions") or {})
    previous = str(versions.get(key) or "")
    steps: list[dict[str, Any]] = []
    outcome = "verified"
    failed_step = ""
    after = dict(HEALTHY)
    for step in steps_for(strategy):
        injected = _injected(fail_at, env, step)
        signals = dict(FAILED if injected else HEALTHY)
        steps.append({"step": step, "result": "failed" if injected else "ok", "signals": signals})
        after = signals
        if injected:
            outcome = "failed"
            failed_step = step
            break
    if outcome == "verified":
        previous_map = dict(state.get("previous") or {})
        previous_map[key] = previous
        versions[key] = version
        state["previous"] = previous_map
        state["versions"] = versions
    elif env == "PROD" and ci not in failed:
        failed.append(ci)
        state["failed_prod"] = failed
    result = {
        "kind": "deploy",
        "outcome": outcome,
        "environment": env,
        "ci": ci,
        "version": version if outcome == "verified" else previous,
        "previous_version": previous,
        "failed_step": failed_step,
        "before": dict(HEALTHY),
        "after": after,
        "steps": steps,
        "replayed": False,
        "rolled_back": False,
    }
    threads = dict(state.get("threads") or {})
    threads[thread_id] = result
    state["threads"] = threads
    _save(path, state)
    return result


def agent_outcome(path: Path, thread_id: str) -> str:
    current = (_load(path).get("threads") or {}).get(thread_id) or {}
    return str(current.get("agent_outcome") or "")


def set_agent_outcome(path: Path, thread_id: str, outcome: str) -> None:
    state = _load(path)
    threads = dict(state.get("threads") or {})
    current = dict(threads.get(thread_id) or {})
    if current.get("agent_outcome"):
        return
    current["agent_outcome"] = outcome
    threads[thread_id] = current
    state["threads"] = threads
    _save(path, state)


def block_prod(path: Path, ci: str, environment: str) -> None:
    if environment.upper() != "PROD":
        return
    state = _load(path)
    failed = list(state.get("failed_prod") or [])
    if ci in failed:
        return
    failed.append(ci)
    state["failed_prod"] = failed
    _save(path, state)


def run_rollback(
    path: Path,
    *,
    thread_id: str,
    ci: str,
    environment: str,
    fail: bool,
) -> dict[str, Any]:
    """Restore the previous version. A failed PROD flag stays set."""
    state = _load(path)
    threads = dict(state.get("threads") or {})
    existing = threads.get(thread_id)
    if isinstance(existing, dict) and existing.get("rolled_back"):
        replay = dict(existing["rollback"])
        replay["replayed"] = True
        return replay
    env = environment.upper()
    key = f"{ci}|{env}"
    if fail:
        result = {
            "outcome": "rollback_failed",
            "environment": env,
            "ci": ci,
            "version": str((state.get("versions") or {}).get(key) or ""),
            "after": dict(FAILED),
            "replayed": False,
        }
    else:
        versions = dict(state.get("versions") or {})
        installed = str(versions.get(key) or "")
        deploy_outcome = str(existing.get("outcome") or "") if isinstance(existing, dict) else ""
        if deploy_outcome == "failed":
            restored = installed
        else:
            restored = str((state.get("previous") or {}).get(key) or "")
            versions[key] = restored
            state["versions"] = versions
        result = {
            "outcome": "rolled_back",
            "environment": env,
            "ci": ci,
            "version": restored,
            "after": dict(HEALTHY),
            "replayed": False,
        }
    if isinstance(existing, dict):
        existing = dict(existing)
        existing["rolled_back"] = True
        existing["rollback"] = result
        threads[thread_id] = existing
        state["threads"] = threads
    _save(path, state)
    return result


def _injected(fail_at: dict[str, Any] | None, environment: str, step: str) -> bool:
    if not isinstance(fail_at, dict):
        return False
    env = str(fail_at.get("env") or "").upper()
    name = str(fail_at.get("step") or "")
    return env == environment and name == step


def _load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SimulatorError("simulator state is not an object")
    return payload


def _save(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
