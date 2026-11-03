"""Release graph. Readiness runs before authorization. Go/no-go runs after it.

docs/DISCOVERY.md item 10. The release is a normal change. Its authorization
is the go-live authorization: Change Management at Assess, then CAB Approval
at Authorize. A failed readiness check does not move the release to Assess.
"""

from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from cm_agents.agents.authorization import record_go_no_go, run_authorization
from cm_agents.agents.release import (
    apply_release_risk,
    run_readiness,
    run_release_close,
    run_release_deploy,
)
from cm_agents.graphs.state import ReleaseState


def build_release_graph(checkpointer: Any) -> Any:
    graph = StateGraph(ReleaseState)
    graph.add_node("readiness", run_readiness)
    graph.add_node("readiness_wait", _readiness_wait)
    graph.add_node("risk", apply_release_risk)
    graph.add_node("authorization", run_authorization)
    graph.add_node("auth_wait", _auth_wait)
    graph.add_node("go_no_go", _go_no_go)
    graph.add_node("deploy", run_release_deploy)
    graph.add_node("review", run_release_close)
    graph.add_edge(START, "readiness")
    graph.add_conditional_edges(
        "readiness",
        _after_readiness,
        {"wait": "readiness_wait", "risk": "risk", "end": END},
    )
    graph.add_edge("readiness_wait", "readiness")
    graph.add_conditional_edges("risk", _after_risk, {"authorization": "authorization", "end": END})
    graph.add_conditional_edges(
        "authorization",
        _after_authorization,
        {"authorization": "auth_wait", "go_no_go": "go_no_go", "end": END},
    )
    graph.add_edge("auth_wait", "authorization")
    graph.add_conditional_edges("go_no_go", _after_go, {"deploy": "deploy", "end": END})
    graph.add_conditional_edges("deploy", _after_deploy, {"review": "review", "end": END})
    graph.add_edge("review", END)
    return graph.compile(checkpointer=checkpointer)


def _after_readiness(state: ReleaseState) -> str:
    if state.get("error"):
        return "end"
    if (state.get("readiness") or {}).get("passed"):
        return "risk"
    return "wait"


def _after_risk(state: ReleaseState) -> str:
    if state.get("error"):
        return "end"
    return "authorization"


def _after_authorization(state: ReleaseState) -> str:
    route = str((state.get("authorization") or {}).get("route") or "")
    if route == "authorization":
        return "authorization"
    if route == "go_no_go":
        return "go_no_go"
    return "end"


def _after_go(state: ReleaseState) -> str:
    choice = str(((state.get("authorization") or {}).get("go_no_go") or {}).get("decision") or "")
    if choice == "go":
        return "deploy"
    return "end"


def _after_deploy(state: ReleaseState) -> str:
    if state.get("error"):
        return "end"
    if str((state.get("deployment") or {}).get("outcome") or "") == "verified":
        return "review"
    return "end"


def _readiness_wait(state: ReleaseState) -> dict[str, Any]:
    interrupt(
        {
            "kind": "requester_info",
            "step": "readiness",
            "change_number": state.get("change_number") or "",
            "state": "-5",
            "detail": str((state.get("readiness") or {}).get("detail") or ""),
        }
    )
    return {}


def _auth_wait(state: ReleaseState) -> dict[str, Any]:
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


def _go_no_go(state: ReleaseState) -> dict[str, Any]:
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
