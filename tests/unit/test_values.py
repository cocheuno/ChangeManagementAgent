from cm_agents.data.load import values_match


def test_values_match_treats_booleans_and_blanks_as_service_now_does() -> None:
    assert values_match(False, "false")
    assert values_match(False, "0")
    assert values_match(True, "true")
    assert values_match("", None)
    assert values_match("3", "3")
    assert not values_match("approved", "requested")
    assert not values_match(False, "true")
