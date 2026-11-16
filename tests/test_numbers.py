from crew_roster.agent.numbers import check_numbers, extract


def values(text):
    return [v for _, v in extract(text)]


def test_extract_ignores_ids_and_reads_durations_and_clocks():
    assert values("DEL-C04 flies SK115-D2 on duty BOM-D3-05 (D3)") == []
    assert values("8h30 then 06:15, 35 h and 7.5") == [8.5, 6.25, 35.0, 7.5]
    assert values("ruleset dgca_dec2025_exemption") == []


def test_minutes_convert_only_from_the_question_not_from_tools():
    src = ['{"used_minutes": 510, "limit_hours": 35.0}']
    assert not check_numbers("8.5 hours used of 35", src).ok
    assert check_numbers("510 minutes used of 35", src).ok
    question = ["Delay SK115 by 90 minutes"]
    assert check_numbers("That is 1.5 hours.", [], convertible=question).ok
    assert check_numbers("About 1h30 late.", [], convertible=question).ok
    assert check_numbers("90 minutes late.", [], convertible=question).ok


def test_real_tool_output_does_not_ground_converted_numbers():
    from crew_roster.agent.tools import Toolbox

    box = Toolbox("dgca_current", [])
    out = next(t for t in box.tools if t.name == "get_roster").invoke({"day": 1})
    assert not check_numbers("You have 60 hours left.", [out]).ok
    assert not check_numbers("That needs 300 pilots.", [out]).ok


def test_rounding_to_one_decimal_is_allowed_but_new_numbers_are_not():
    src = ['{"remaining_hours": 26.67}']
    assert check_numbers("26.7 hours remain", src).ok
    res = check_numbers("27.9 hours remain after 3 duties", src)
    assert not res.ok and res.ungrounded == ["27.9", "3"]


def test_trivial_numbers_and_question_numbers():
    assert check_numbers("1 change was needed", []).ok
    assert check_numbers("Delaying by 240 minutes is fine", ["delay SK115 by 240 minutes"]).ok
