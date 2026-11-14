"""Scenario runner. No network."""

from cm_agents.scenarios import ScenarioError, run_scenarios, scenario_names


def test_all_runs_each_scenario_file_once(monkeypatch, capsys) -> None:
    calls: list[str] = []
    removed: list[object] = []

    def runner(path: str) -> int:
        calls.append(path)
        return 0

    monkeypatch.setattr(
        "cm_agents.scenarios.describe_state",
        lambda: "failed_prod=[] version_count=0",
    )
    monkeypatch.setattr(
        "cm_agents.scenarios.remove_scenario_records",
        lambda settings: removed.append(settings) or 0,
    )
    code = run_scenarios(object(), "all", runner=runner)  # type: ignore[arg-type]
    assert code == 0
    assert calls == [
        "tests/live/test_s01.py",
        "tests/live/test_s02_close.py",
        "tests/live/test_s03.py",
        "tests/live/test_s04.py",
        "tests/live/test_s05.py",
        "tests/live/test_s06.py",
        "tests/live/test_s07.py",
        "tests/live/test_s08.py",
        "tests/live/test_s09.py",
    ]
    assert calls.count("tests/live/test_s09.py") == 1
    assert "tests/live/test_s02.py" not in calls
    assert len(removed) == 9
    assert "simulator state: failed_prod=[] version_count=0" in capsys.readouterr().out


def test_a_failed_scenario_stops_before_the_next_one(monkeypatch) -> None:
    calls: list[str] = []

    def runner(path: str) -> int:
        calls.append(path)
        return 1 if path.endswith("test_s03.py") else 0

    monkeypatch.setattr(
        "cm_agents.scenarios.describe_state",
        lambda: "failed_prod=[] version_count=0",
    )
    monkeypatch.setattr(
        "cm_agents.scenarios.remove_scenario_records",
        lambda _settings: calls.append("removed") or 0,
    )
    code = run_scenarios(object(), "all", runner=runner)  # type: ignore[arg-type]
    assert code == 1
    assert calls == [
        "tests/live/test_s01.py",
        "removed",
        "tests/live/test_s02_close.py",
        "removed",
        "tests/live/test_s03.py",
    ]


def test_s10_uses_the_s09_file() -> None:
    assert scenario_names("S10") == ["S10"]
    try:
        scenario_names("S11")
    except ScenarioError as exc:
        assert "S11" in str(exc)
    else:
        raise AssertionError("S11 should be rejected")
