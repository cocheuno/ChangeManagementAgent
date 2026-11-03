from cm_agents.deploy.simulator import (
    HEALTHY,
    STRATEGIES,
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


def test_each_strategy_deploys_when_nothing_is_injected(tmp_path) -> None:
    for name, steps in STRATEGIES.items():
        if name in {"blue_green", "big_bang"}:
            continue
        result = run_deploy(
            tmp_path / f"{name}.json",
            thread_id=f"SYN-{name}",
            ci="syn-app",
            environment="PROD",
            strategy=name,
            version="v2",
            fail_at=None,
        )
        assert result["outcome"] == "verified"
        assert [step["step"] for step in result["steps"]] == list(steps)
        assert result["version"] == "v2"
        assert passes_thresholds(result["before"], result["after"], POLICY)


def test_canary_failure_blocks_a_later_prod_deploy_and_rollback_restores(tmp_path) -> None:
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
    try:
        run_deploy(
            path,
            thread_id="SYN-retry",
            ci="syn-ful-api",
            environment="PROD",
            strategy="canary",
            version="v3",
            fail_at=None,
        )
    except RedeployBlocked:
        blocked = True
    else:
        blocked = False
    assert blocked
    rolled = run_rollback(
        path, thread_id="SYN-fail", ci="syn-ful-api", environment="PROD", fail=False
    )
    assert rolled["outcome"] == "rolled_back"
    assert rolled["after"] == HEALTHY
    assert passes_thresholds(HEALTHY, rolled["after"], POLICY)
    try:
        run_deploy(
            path,
            thread_id="SYN-after-rollback",
            ci="syn-ful-api",
            environment="PROD",
            strategy="big bang",
            version="v4",
            fail_at=None,
        )
    except RedeployBlocked:
        still_blocked = True
    else:
        still_blocked = False
    assert still_blocked


def test_stage_failure_does_not_block_prod(tmp_path) -> None:
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
