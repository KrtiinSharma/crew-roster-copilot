from crew_roster.agent.numbers import check_numbers, extract


def values(text):
    return [v for _, v in extract(text)]


def test_extract_ignores_ids_and_reads_durations_and_clocks():
    assert values("DEL-C04 flies SK115-D2 on duty BOM-D3-05 (D3)") == []
    assert values("8h30 then 06:15, 35 h and 7.5") == [8.5, 6.25, 35.0, 7.5]
    assert values("ruleset dgca_dec2025_exemption") == []


def test_minutes_in_tools_ground_hours_in_the_answer():
    src = ['{"used_minutes": 510, "limit_hours": 35.0}']
    assert check_numbers("8.5 hours used of 35", src).ok
    assert check_numbers("8h30 used", src).ok
    assert check_numbers("about 8.5h", src).ok


def test_rounding_to_one_decimal_is_allowed_but_new_numbers_are_not():
    src = ['{"remaining_hours": 26.67}']
    assert check_numbers("26.7 hours remain", src).ok
    res = check_numbers("27.9 hours remain after 3 duties", src)
    assert not res.ok and res.ungrounded == ["27.9", "3"]


def test_trivial_numbers_and_question_numbers():
    assert check_numbers("1 change was needed", []).ok
    assert check_numbers("Delaying by 240 minutes is fine", ["delay SK115 by 240 minutes"]).ok
