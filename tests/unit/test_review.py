"""Review close codes and the PIR rule. No network and no model."""

from cm_agents.agents.context import AgentContext, activate, reset
from cm_agents.agents.review import _close_code, _pir_required
from cm_agents.enablement.policy import load_policy


def test_rolled_back_closes_unsuccessful() -> None:
    assert _close_code({"outcome": "rolled_back", "priority": ""}) == "unsuccessful"


def test_priority_1_through_3_closes_unsuccessful() -> None:
    for priority in ("1", "2", "3"):
        assert _close_code({"outcome": "verified", "priority": priority}) == "unsuccessful"


def test_priority_4_closes_successful_with_issues() -> None:
    assert _close_code({"outcome": "verified", "priority": "4"}) == "successful_issues"


def test_a_verified_deploy_closes_successful() -> None:
    assert _close_code({"outcome": "verified", "priority": ""}) == "successful"


def test_pir_is_required_for_unsuccessful_emergency_high_risk_and_caused_incident() -> None:
    token = _activate()
    try:
        assert _pir_required({"change_type": "normal"}, "unsuccessful", {})
        assert _pir_required({"change_type": "emergency"}, "successful", {})
        assert _pir_required({"change_type": "normal", "risk": {"tier": "high"}}, "successful", {})
        assert _pir_required({"change_type": "normal"}, "successful", {"incident": "INC001"})
    finally:
        reset(token)


def test_pir_is_not_required_for_a_successful_normal_change() -> None:
    token = _activate()
    try:
        assert not _pir_required(
            {"change_type": "normal", "risk": {"tier": "low"}},
            "successful",
            {},
        )
    finally:
        reset(token)


def _activate():
    return activate(
        AgentContext(
            object(),  # type: ignore[arg-type]
            object(),  # type: ignore[arg-type]
            load_policy(),
            {},
        )
    )
