from cm_agents.data.teardown import baseline_lines


def test_rows_created_after_the_seed_do_not_fail_the_baseline() -> None:
    ok, text = baseline_lines("task_ci", 313, 313, 4)
    assert ok
    assert text == "task_ci before_seed=313 baseline=313 created_after_seed=4"


def test_missing_rows_from_before_the_seed_fail_the_baseline() -> None:
    ok, text = baseline_lines("task_ci", 313, 312, 5)
    assert not ok
    assert "before_seed=312" in text
    assert "created_after_seed=5" in text
