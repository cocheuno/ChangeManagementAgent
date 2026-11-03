from langgraph.checkpoint.sqlite import SqliteSaver

from cm_agents.graphs.change_graph import _after_go, build_change_graph


def test_change_graph_compiles_with_the_sqlite_checkpointer() -> None:
    with SqliteSaver.from_conn_string(":memory:") as saver:
        graph = build_change_graph(saver)
        assert "auth_wait" in graph.nodes
        assert "go_no_go" in graph.nodes
        assert "deployment" in graph.nodes
        assert "review" in graph.nodes


def test_a_go_decision_deploys_and_a_bare_resume_stops() -> None:
    assert _after_go({"authorization": {"go_no_go": {"decision": "go"}}}) == "deployment"
    assert _after_go({"authorization": {"go_no_go": {"decision": "no-go"}}}) == "scheduling"
    assert _after_go({"authorization": {"route": "go_no_go"}}) == "end"
