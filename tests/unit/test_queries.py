from cm_agents.data.queries import (
    SCENARIO_CORRELATION,
    counts_in_metrics,
    metric_change_query,
    metric_incident_query,
)


def test_phase5_metrics_count_seed_prefixes_only() -> None:
    assert counts_in_metrics("SYN-CHG-0001")
    assert counts_in_metrics("SYN-OPEN-22")
    assert counts_in_metrics("SYN-REL-store-2026.01.0")
    assert counts_in_metrics("SYN-INC-0001")
    assert not counts_in_metrics("SYN-S02-eb66bb0a")
    assert not counts_in_metrics("SYN-S05-trigger")
    assert not counts_in_metrics("SYN-" + "ab12cd34ef56")
    assert metric_change_query() == (
        "correlation_idSTARTSWITHSYN-CHG-"
        "^ORcorrelation_idSTARTSWITHSYN-OPEN-"
        "^ORcorrelation_idSTARTSWITHSYN-REL-"
    )
    assert metric_incident_query() == "correlation_idSTARTSWITHSYN-INC-"
    assert "NOT LIKESYN-CHG-" in SCENARIO_CORRELATION
    assert "NOT LIKESYN-INC-" in SCENARIO_CORRELATION
