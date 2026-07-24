"""Pool date-window defaults for consensus selection."""

from consensus.runs_store import PERIOD_MONTHS_DEFAULT


def test_period_months_default_is_three():
    assert PERIOD_MONTHS_DEFAULT == 3
