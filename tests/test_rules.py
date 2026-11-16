import pytest

from crew_roster.rules import RULESETS, load


def test_both_rulesets_load_in_minutes():
    cur, exm = load("dgca_current"), load("dgca_dec2025_exemption")
    assert set(RULESETS) == {"dgca_current", "dgca_dec2025_exemption"}
    assert cur.max_ft_per_duty == 8 * 60
    assert cur.min_rest == 12 * 60
    assert cur.ft_7d == 35 * 60 and cur.ft_28d == 100 * 60
    assert cur.duty_7d == 60 * 60 and cur.duty_28d == 190 * 60
    assert (cur.night_start, cur.night_end) == (0, 360)
    assert cur.night_max_landings == 2 and exm.night_max_landings == 6
    assert cur.max_consecutive_nights == 2
    assert cur.max_fdp_by_landings[1] >= cur.max_fdp_by_landings[6]
    assert set(cur.sources) >= {"max_ft_per_duty", "min_rest", "weekly_rest", "night_window"}


def test_unknown_ruleset_is_rejected():
    with pytest.raises(ValueError):
        load("nope")
