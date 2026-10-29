from cm_agents.enablement.risk_score import score_historical


def test_a_canceled_change_without_a_planned_start_is_scored() -> None:
    fixtures = {
        "changes": [
            {
                "key": "SYN-CAN-1",
                "kind": "historical",
                "type": "normal",
                "state": "4",
                "service": "SYN HR Portal",
                "ci_class": "cmdb_ci_appl",
                "cmdb_ci": "syn-hr-portal",
                "deployment_method": "automated",
                "plan_quality": {
                    "ordered_backout": True,
                    "backout_trigger": True,
                    "test_criteria": True,
                    "implementation_owner": True,
                },
                "start_date": "",
                "end_date": "",
                "opened_at": "2026-06-02 14:00:00",
                "closed_at": "",
                "close_code": "",
            }
        ],
        "cis": [
            {
                "name": "syn-hr-portal",
                "service": "SYN HR Portal",
                "ci_class": "cmdb_ci_appl",
            }
        ],
        "relationships": [],
        "task_ci": [],
        "incidents": [],
        "services": [{"name": "SYN HR Portal", "tier": 3}],
    }
    policy = {
        "risk": {
            "factors": {
                "service_criticality": {"tier1": 3, "tier2": 2, "tier3": 1},
                "impacted_services": {"1": 0, "2": 2, "3+": 3},
                "similar_change_failure_rate_12m": {"lt_5pct": 0, "5_to_15pct": 2, "gt_15pct": 3},
                "change_caused_incidents_90d": {"0": 0, "1": 1, "2+": 2},
                "deployment_method": {"automated": 0, "manual": 2},
                "outside_maintenance_window": 2,
                "friday_evening_start": 1,
                "plan_quality_failed_check": 1,
                "emergency": 2,
            },
            "tiers": {"high": 10, "moderate": 6},
        }
    }
    scored = score_historical(fixtures, policy)
    assert len(scored) == 1
    assert scored[0]["key"] == "SYN-CAN-1"
