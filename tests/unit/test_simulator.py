"""Deterministic simulator cases. No network and no model."""

from pathlib import Path

from cm_agents.deploy.simulator import (
    FAILED,
    HEALTHY,
    RedeployBlocked,
    passes_thresholds,
    run_deploy,
    run_rollback,
)

POLICY = {
    "verification": {
        "error_rate_max_pct": 2.0,
        "p95_latency_max_increase_pct": 20,
        "availability_min_pct": 99.5,
    }
}


def test_canary_succeeds(tmp_path: Path) -> None:
    result = _deploy(tmp_path, "canary", fail_at=None)
    assert result["outcome"] == "verified"
    assert [step["step"] for step in result["steps"]] == ["canary_10", "canary_100"]
    assert result["version"] == "v2"
    assert passes_thresholds(result["before"], result["after"], POLICY)


def test_blue_green_succeeds(tmp_path: Path) -> None:
    result = _deploy(tmp_path, "blue/green", fail_at=None)
    assert result["outcome"] == "verified"
    assert [step["step"] for step in result["steps"]] == ["switch"]
    assert result["version"] == "v2"
    assert passes_thresholds(result["before"], result["after"], POLICY)


def test_rolling_succeeds(tmp_path: Path) -> None:
    result = _deploy(tmp_path, "rolling", fail_at=None)
    assert result["outcome"] == "verified"
    assert [step["step"] for step in result["steps"]] == [
        "batch_25",
        "batch_50",
        "batch_75",
        "batch_100",
    ]
    assert result["version"] == "v2"
    assert passes_thresholds(result["before"], result["after"], POLICY)


def test_big_bang_succeeds(tmp_path: Path) -> None:
    result = _deploy(tmp_path, "big bang", fail_at=None)
    assert result["outcome"] == "verified"
    assert [step["step"] for step in result["steps"]] == ["all"]
    assert result["version"] == "v2"
    assert passes_thresholds(result["before"], result["after"], POLICY)


def test_canary_injected_failure_stops_at_canary_100(tmp_path: Path) -> None:
    _assert_failure(tmp_path, "canary", "canary_100", ["ok", "failed"])


def test_blue_green_injected_failure_stops_at_switch(tmp_path: Path) -> None:
    _assert_failure(tmp_path, "blue/green", "switch", ["failed"])


def test_rolling_injected_failure_stops_at_batch_75(tmp_path: Path) -> None:
    _assert_failure(tmp_path, "rolling", "batch_75", ["ok", "ok", "failed"])


def test_big_bang_injected_failure_stops_at_all(tmp_path: Path) -> None:
    _assert_failure(tmp_path, "big bang", "all", ["failed"])


def test_canary_rollback_restores_the_previous_version_and_keeps_prod_blocked(
    tmp_path: Path,
) -> None:
    _assert_rollback(tmp_path, "canary", "canary_100")


def test_blue_green_rollback_restores_the_previous_version_and_keeps_prod_blocked(
    tmp_path: Path,
) -> None:
    _assert_rollback(tmp_path, "blue/green", "switch")


def test_rolling_rollback_restores_the_previous_version_and_keeps_prod_blocked(
    tmp_path: Path,
) -> None:
    _assert_rollback(tmp_path, "rolling", "batch_75")


def test_big_bang_rollback_restores_the_previous_version_and_keeps_prod_blocked(
    tmp_path: Path,
) -> None:
    _assert_rollback(tmp_path, "big bang", "all")


def test_canary_failure_blocks_a_later_prod_deploy_and_rollback_restores(tmp_path: Path) -> None:
    path = tmp_path / "sim.json"
    failed = run_deploy(
        path,
        thread_id="SYN-fail",
        ci="syn-ful-api",
        environment="PROD",
        strategy="canary",
        version="v2",
        fail_at={"env": "PROD", "step": "canary_100"},
    )
    assert [step["result"] for step in failed["steps"]] == ["ok", "failed"]
    assert failed["version"] != "v2"
    assert not passes_thresholds(failed["before"], failed["after"], POLICY)
    replay = run_deploy(
        path,
        thread_id="SYN-fail",
        ci="syn-ful-api",
        environment="PROD",
        strategy="canary",
        version="v2",
        fail_at={"env": "PROD", "step": "canary_100"},
    )
    assert replay["replayed"] is True
    assert len(replay["steps"]) == 2
    _expect_blocked(path, "SYN-retry", "syn-ful-api", "canary", "v3")
    rolled = run_rollback(
        path, thread_id="SYN-fail", ci="syn-ful-api", environment="PROD", fail=False
    )
    assert rolled["outcome"] == "rolled_back"
    assert rolled["after"] == HEALTHY
    assert passes_thresholds(HEALTHY, rolled["after"], POLICY)
    _expect_blocked(path, "SYN-after-rollback", "syn-ful-api", "big bang", "v4")


def test_stage_failure_does_not_block_prod(tmp_path: Path) -> None:
    path = tmp_path / "sim.json"
    failed = run_deploy(
        path,
        thread_id="SYN-stage",
        ci="syn-store-lb-05",
        environment="STAGE",
        strategy="big bang",
        version="v2",
        fail_at={"env": "STAGE", "step": "all"},
    )
    assert failed["outcome"] == "failed"
    prod = run_deploy(
        path,
        thread_id="SYN-prod",
        ci="syn-store-lb-05",
        environment="PROD",
        strategy="big bang",
        version="v2",
        fail_at=None,
    )
    assert prod["outcome"] == "verified"


def _deploy(tmp_path: Path, strategy: str, *, fail_at: dict[str, str] | None) -> dict:
    return run_deploy(
        tmp_path / "sim.json",
        thread_id=f"SYN-{strategy}",
        ci="syn-app",
        environment="PROD",
        strategy=strategy,
        version="v2",
        fail_at=fail_at,
    )


def _assert_failure(tmp_path: Path, strategy: str, step: str, results: list[str]) -> None:
    failed = _deploy(tmp_path, strategy, fail_at={"env": "PROD", "step": step})
    assert [row["result"] for row in failed["steps"]] == results
    assert failed["outcome"] == "failed"
    assert failed["failed_step"] == step
    assert failed["version"] != "v2"
    assert failed["after"] == FAILED
    assert not passes_thresholds(failed["before"], failed["after"], POLICY)


def _assert_rollback(tmp_path: Path, strategy: str, step: str) -> None:
    path = tmp_path / "sim.json"
    ci = "syn-app"
    run_deploy(
        path,
        thread_id="SYN-old",
        ci=ci,
        environment="PROD",
        strategy="big bang",
        version="v1",
        fail_at=None,
    )
    failed = run_deploy(
        path,
        thread_id="SYN-new",
        ci=ci,
        environment="PROD",
        strategy=strategy,
        version="v2",
        fail_at={"env": "PROD", "step": step},
    )
    assert failed["outcome"] == "failed"
    assert failed["version"] == "v1"
    rolled = run_rollback(path, thread_id="SYN-new", ci=ci, environment="PROD", fail=False)
    assert rolled["outcome"] == "rolled_back"
    assert rolled["version"] == "v1"
    assert rolled["after"] == HEALTHY
    assert passes_thresholds(HEALTHY, rolled["after"], POLICY)
    _expect_blocked(path, "SYN-later", ci, strategy, "v3")


def _expect_blocked(path: Path, thread_id: str, ci: str, strategy: str, version: str) -> None:
    try:
        run_deploy(
            path,
            thread_id=thread_id,
            ci=ci,
            environment="PROD",
            strategy=strategy,
            version=version,
            fail_at=None,
        )
    except RedeployBlocked:
        return
    raise AssertionError(f"PROD deploy for {ci} was not blocked")
