"""todira_common.switches: an unset switch keeps its caller's default; the dashboard's choice wins once set."""
from unittest.mock import patch

from todira_common import switches


def test_unset_switch_keeps_the_default_and_a_set_one_wins():
    switches._cache.clear()
    with patch.object(switches, "get_flag", lambda session, key: None), patch.object(switches, "get_session"):
        assert switches.is_on("voice", True) is True
        assert switches.is_on("share_button", False) is False
    switches._cache.clear()
    with patch.object(switches, "get_flag", lambda session, key: "0"), patch.object(switches, "get_session"):
        assert switches.is_on("voice", True) is False
    switches._cache.clear()


def test_a_database_problem_falls_back_to_the_default():
    switches._cache.clear()
    with patch.object(switches, "get_session", side_effect=RuntimeError("db down")):
        assert switches.is_on("facebook", True) is True
