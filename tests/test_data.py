from crew_roster.data import BASES, GROUND_MIN, TURN_TEMPLATES, generate
from crew_roster.models import DAY, Duty, Roster, is_night


def test_generator_is_deterministic():
    assert generate().model_dump() == generate().model_dump()


def test_flights_form_out_and_back_turns(airline):
    per_day = 2 * sum(len(t) for t in TURN_TEMPLATES.values())
    assert len(airline.flights) == per_day * airline.days
    assert 40 <= per_day <= 46
    for turn in airline.turns.values():
        out, back = (airline.flights[f] for f in turn.flight_ids)
        assert out.origin == turn.base == back.dest
        assert out.dest == back.origin == turn.dest
        assert back.dep - out.arr == GROUND_MIN


def test_sixty_pilots_split_by_base_and_rank(airline):
    assert len(airline.pilots) == 60
    for base in BASES:
        ranks = [p.rank for p in airline.pilots if p.base == base]
        assert ranks.count("CPT") == 15 and ranks.count("FO") == 15
    assert len({p.id for p in airline.pilots}) == 60


def test_history_is_in_the_past_and_has_weekly_rest(airline):
    for p in airline.pilots:
        hist = airline.history[p.id]
        assert hist, p.id
        assert all(h.release <= 0 for h in hist)
        busy = {k for h in hist for k in h.touched_days()}
        for t in range(-21, 0):
            assert any(s not in busy and s + 1 not in busy for s in range(t - 6, t)), (p.id, t)
        assert sum(h.flight_time for h in hist if h.day >= -27) < 100 * 60


def test_some_pilots_have_leave(airline):
    on_leave = [p for p in airline.pilots if p.unavailable_days]
    assert len(on_leave) == 6
    assert all(0 <= d < airline.days for p in on_leave for d in p.unavailable_days)


def test_is_night_and_duty_helpers():
    assert is_night(23 * 60, 30 * 60, 0, 360)  # 23:00 -> 06:00 next day
    assert is_night(5 * 60, 9 * 60, 0, 360)  # report 05:00
    assert not is_night(6 * 60, 18 * 60, 0, 360)  # 06:00 -> 18:00
    d = Duty(
        id="X",
        base="DEL",
        report=DAY + 22 * 60,
        release=2 * DAY + 2 * 60,
        flight_time=200,
        landings=2,
        night=True,
    )
    assert d.day == 1 and d.length == 240 and list(d.touched_days()) == [1, 2]


def test_roster_helpers_are_immutable():
    r = Roster(assignments={"D1": {"CPT": "A"}})
    r2 = r.with_slot("D1", "FO", "B")
    assert r.get("D1", "FO") is None and r2.get("D1", "FO") == "B"
    assert r2.duties_of("B") == [("D1", "FO")]
    assert r2.with_slot("D1", "CPT", None).with_slot("D1", "FO", None).assignments == {}
