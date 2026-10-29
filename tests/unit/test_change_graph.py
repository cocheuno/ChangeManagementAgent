from langgraph.checkpoint.sqlite import SqliteSaver

from cm_agents.graphs.change_graph import build_change_graph


def test_change_graph_compiles_with_the_sqlite_checkpointer() -> None:
    with SqliteSaver.from_conn_string(":memory:") as saver:
        graph = build_change_graph(saver)
        assert "auth_wait" in graph.nodes
        assert "go_no_go" in graph.nodes
