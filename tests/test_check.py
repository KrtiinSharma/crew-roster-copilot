from factories import mk_duty, mk_history, mk_pilot, mk_problem, mk_roster

from crew_roster.roster.check import check

CPT = mk_pilot("P1")


def rules_of(violations):
    return {v.rule for v in violations}


def run(duties, pilots=(CPT,), role="CPT", pid="P1", **kw):
    p = mk_problem(list(duties), list(pilots), **kw)
    return check(p, mk_roster({d.id: {role: pid} for d in duties}))


def series(days, start="06:00", hours=9, ft_hours=7):
    return [mk_duty(f"D{k}", k, start, hours, ft_hours=ft_hours) for k in days]


def test_legal_day_duty_has_no_violations():
    assert run([mk_duty("D1", 1, "06:00", 8, ft_hours=6)]) == []


def test_flight_time_per_duty_over_8h():
    assert "max_ft_per_duty" in rules_of(run([mk_duty("D1", 1, "06:00", 10, ft_hours=8.5)]))


def test_fdp_limit_shrinks_with_landings():
    assert "max_fdp" in rules_of(run([mk_duty("D1", 1, "06:00", 12.5, ft_hours=7, landings=4)]))
    assert "max_fdp" not in rules_of(run([mk_duty("D1", 1, "06:00", 12.5, ft_hours=7)]))


def test_night_landings_current_vs_exemption():
    d = mk_duty("D1", 1, "23:00", 8, ft_hours=5, landings=4)
    assert "night_max_landings" in rules_of(run([d]))
    assert "night_max_landings" not in rules_of(run([d], ruleset="dgca_dec2025_exemption"))


def test_night_duty_period_cap():
    assert "night_max_fdp" in rules_of(run([mk_duty("D1", 1, "22:00", 10.5, ft_hours=6)]))


def test_min_rest_12h():
    d1 = mk_duty("D1", 1, "06:00", 10, ft_hours=6)  # release 16:00
    assert "min_rest" in rules_of(run([d1, mk_duty("D2", 2, "02:00", 6, ft_hours=4)]))
    assert "min_rest" not in rules_of(run([d1, mk_duty("D2", 2, "05:00", 6, ft_hours=4)]))


def test_rest_at_least_previous_duty_length():
    d1 = mk_duty("D1", 1, "06:00", 13, ft_hours=7)  # release 19:00 -> needs 13 h
    assert "min_rest" in rules_of(run([d1, mk_duty("D2", 2, "07:30", 6, ft_hours=4)]))
    assert "min_rest" not in rules_of(run([d1, mk_duty("D2", 2, "08:00", 6, ft_hours=4)]))


def test_flight_time_35h_in_7_days():
    assert "ft_7d" in rules_of(run(series([0, 1, 2, 3, 4], ft_hours=7.5)))
    assert "ft_7d" not in rules_of(run(series([0, 1, 2, 3, 4], ft_hours=7)))


def test_duty_60h_in_7_days():
    assert "duty_7d" in rules_of(run(series(range(6), hours=10.5, ft_hours=5)))
    assert "duty_7d" not in rules_of(run(series(range(5), hours=11, ft_hours=5)))


ON_DAYS = [d for d in range(-27, 0) if d % 6 not in (0, 1)]  # 19 history duties


def test_flight_time_100h_in_28_days_counts_history():
    hot = mk_history("P1", ON_DAYS, hours=8, ft_hours=6)  # 114 h
    cool = mk_history("P1", ON_DAYS, hours=8, ft_hours=4.5)  # 85.5 h
    assert "ft_28d" in rules_of(run(series([0]), history=hot))
    assert "ft_28d" not in rules_of(run(series([0]), history=cool))


def test_duty_190h_in_28_days_counts_history():
    hot = mk_history("P1", ON_DAYS, hours=10.5, ft_hours=4)  # 199.5 h
    cool = mk_history("P1", ON_DAYS, hours=9, ft_hours=4)  # 171 h
    assert "duty_28d" in rules_of(run(series([0]), history=hot))
    assert "duty_28d" not in rules_of(run(series([0]), history=cool))


def test_weekly_rest_needs_two_consecutive_free_days():
    assert "weekly_rest" in rules_of(run(series([0, 1, 2, 3, 4], ft_hours=5)))
    assert "weekly_rest" not in rules_of(run(series([0, 1, 2, 3, 6], ft_hours=5)))


def test_max_two_consecutive_night_duties():
    def nights(days):
        return [mk_duty(f"N{k}", k, "23:00", 7, ft_hours=5) for k in days]

    assert "consecutive_nights" in rules_of(run(nights([0, 1, 2])))
    assert "consecutive_nights" not in rules_of(run(nights([0, 1, 3])))


def test_leave_and_sick_days():
    d = mk_duty("D1", 2, "06:00", 8, ft_hours=6)
    assert "unavailable" in rules_of(run([d], pilots=[mk_pilot("P1", off=[2])]))
    assert "sick" in rules_of(run([d], sick={"P1": [2]}))


def test_rank_must_match_role():
    d = mk_duty("D1", 2, "06:00", 8, ft_hours=6)
    assert "wrong_rank" in rules_of(run([d], pilots=[mk_pilot("F1", rank="FO")], pid="F1"))


def test_history_only_short_rest_is_not_reported():
    # two past duties only 10 h apart; the roster duty itself is well rested
    hist = {"P1": [mk_duty("H1", -3, "06:00", 10, ft_hours=6),
                   mk_duty("H2", -2, "02:00", 6, ft_hours=4)]}
    assert "min_rest" not in rules_of(run(series([2]), history=hist))
    # but a short rest from the last history duty into the roster is still caught
    late = {"P1": [mk_duty("H1", -1, "12:00", 10, ft_hours=6)]}  # release day 0 -> 22:00 day -1
    assert "min_rest" in rules_of(run([mk_duty("D0", 0, "06:00", 8, ft_hours=6)], history=late))
