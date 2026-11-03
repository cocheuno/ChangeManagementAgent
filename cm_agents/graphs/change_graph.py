"""Change graph through deployment and review.

Authorization interrupts once per approval step. Assess approvals are created
before Authorize approvals exist, so one interrupt cannot cover both.
A go decision, an authorized emergency change, and a compliant standard change
enter deployment. A rejection is recorded in review and is not deployed.
docs/DISCOVERY.md item 5.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from cm_agents.agents.authorization import finish_standard, record_go_no_go, run_authorization
from cm_agents.agents.deployment import run_deployment
from cm_agents.agents.intake import run_intake
from cm_agents.agents.review import run_review
from cm_agents.agents.risk import run_risk
from cm_agents.agents.scheduling import run_scheduling
from cm_agents.graphs.state import ChangeState


def build_change_graph(checkpointer: Any) -> Any:
    graph = StateGraph(ChangeState)
    graph.add_node("intake", run_intake)
    graph.add_node("info_wait", _info_wait)
    graph.add_node("scheduling", run_scheduling)
    graph.add_node("finish_standard", finish_standard)
    graph.add_node("risk", run_risk)
    graph.add_node("authorization", run_authorization)
    graph.add_node("auth_wait", _auth_wait)
    graph.add_node("go_no_go", _go_no_go)
    graph.add_node("deployment", run_deployment)
    graph.add_node("rollback_wait", _rollback_wait)
    graph.add_node("review", run_review)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges(
        "intake",
        _after_intake,
        {"info_wait": "info_wait", "scheduling": "scheduling", "end": END},
    )
    graph.add_edge("info_wait", "intake")
    graph.add_conditional_edges(
        "scheduling",
        _after_schedule,
        {"finish": "finish_standard", "risk": "risk", "end": END},
    )
    graph.add_edge("finish_standard", "deployment")
    graph.add_edge("risk", "authorization")
    graph.add_conditional_edges(
        "authorization",
        _after_authorization,
        {
            "authorization": "auth_wait",
            "go_no_go": "go_no_go",
            "authorized": "deployment",
            "rejected": "review",
            "release_handoff": END,
            "ready": END,
            "recorded": END,
            "end": END,
        },
    )
    graph.add_edge("auth_wait", "authorization")
    graph.add_conditional_edges(
        "go_no_go",
        _after_go,
        {"deployment": "deployment", "scheduling": "scheduling", "end": END},
    )
    graph.add_conditional_edges(
        "deployment",
        _after_deployment,
        {"review": "review", "rollback_wait": "rollback_wait", "end": END},
    )
    graph.add_edge("rollback_wait", END)
    graph.add_edge("review", END)
    return graph.compile(checkpointer=checkpointer)


def _after_intake(state: ChangeState) -> str:
    if state.get("error"):
        return "end"
    if state.get("gaps"):
        return "info_wait"
    return "scheduling"


def _after_schedule(state: ChangeState) -> str:
    if state.get("error"):
        return "end"
    schedule = state.get("schedule") or {}
    if state.get("change_type") == "standard" and schedule.get("compliant"):
        return "finish"
    if state.get("change_type") == "standard":
        return "end"
    return "risk"


def _after_authorization(state: ChangeState) -> str:
    route = str((state.get("authorization") or {}).get("route") or "end")
    if route == "authorization":
        return "authorization"
    if route in {"go_no_go", "authorized", "rejected", "release_handoff", "ready", "recorded"}:
        return route
    return "end"


def _info_wait(state: ChangeState) -> dict[str, Any]:
    patch = interrupt(
        {
            "kind": "requester_info",
            "step": "requester_info",
            "change_number": state.get("change_number") or "",
            "state": "-5",
            "gaps": list(state.get("gaps") or []),
        }
    )
    request = dict(state.get("request") or {})
    if isinstance(patch, dict):
        request.update({key: value for key, value in patch.items() if key != "kind"})
    return {"request": request, "gaps": []}


def _auth_wait(state: ChangeState) -> dict[str, Any]:
    auth = state.get("authorization") or {}
    interrupt(
        {
            "kind": "authorization",
            "step": auth.get("pending_step") or "",
            "change_number": state.get("change_number") or "",
            "state": auth.get("change_state") or "",
        }
    )
    return {}


def _after_go(state: ChangeState) -> str:
    choice = str(((state.get("authorization") or {}).get("go_no_go") or {}).get("decision") or "")
    if choice == "go":
        return "deployment"
    if choice == "no-go":
        return "scheduling"
    return "end"


def _after_deployment(state: ChangeState) -> str:
    if state.get("error"):
        return "end"
    outcome = str((state.get("deployment") or {}).get("outcome") or "")
    if outcome == "rollback_failed":
        return "rollback_wait"
    if outcome in {"verified", "rolled_back"}:
        return "review"
    return "end"


def _go_no_go(state: ChangeState) -> dict[str, Any]:
    decision = interrupt(
        {
            "kind": "go_no_go",
            "step": "go_no_go",
            "change_number": state.get("change_number") or "",
            "state": (state.get("authorization") or {}).get("change_state") or "",
        }
    )
    if isinstance(decision, dict) and decision.get("decision"):
        return record_go_no_go(state, decision)
    return {}


def _rollback_wait(state: ChangeState) -> dict[str, Any]:
    interrupt(
        {
            "kind": "rollback_failed",
            "step": "rollback_failed",
            "change_number": state.get("change_number") or "",
            "state": (state.get("deployment") or {}).get("change_state") or "",
        }
    )
    return {}
