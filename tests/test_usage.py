from factories import mk_duty, mk_pilot, mk_problem, mk_roster

from crew_roster.roster.check import check, pilot_usage


def test_usage_matches_the_checker_on_a_breach():
    duties = [mk_duty(f"D{k}", k, "06:00", 9, ft_hours=7.5) for k in range(5)]  # 37.5 h
    p = mk_problem(duties, [mk_pilot("P1")])
    roster = mk_roster({d.id: {"CPT": "P1"} for d in duties})
    usage = {u.rule: u for u in pilot_usage(p, roster, "P1", 4)}
    assert usage["ft_7d"].used == 2250 and usage["ft_7d"].limit == 2100
    assert usage["ft_7d"].remaining == 0
    breach = next(v for v in check(p, roster) if v.rule == "ft_7d")
    assert (breach.value, breach.limit) == (usage["ft_7d"].used, usage["ft_7d"].limit)


def test_usage_counts_only_the_window_ending_that_day():
    duties = [mk_duty("D0", 0, "06:00", 9, ft_hours=7), mk_duty("D3", 3, "06:00", 9, ft_hours=6)]
    p = mk_problem(duties, [mk_pilot("P1")])
    roster = mk_roster({d.id: {"CPT": "P1"} for d in duties})
    by_day = {d: {u.rule: u.used for u in pilot_usage(p, roster, "P1", d)} for d in (0, 2, 3)}
    assert by_day[0]["ft_7d"] == 420 and by_day[2]["ft_7d"] == 420 and by_day[3]["ft_7d"] == 780
    assert by_day[3]["duty_7d"] == 2 * 540


def test_base_roster_usage_is_within_every_limit(problem, base_result):
    for pid in [p.id for p in problem.pilots][:20]:
        for day in range(problem.horizon_days):
            for u in pilot_usage(problem, base_result.roster, pid, day):
                assert u.used <= u.limit and u.remaining == u.limit - u.used
