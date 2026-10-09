"""Deadline rule engine and .ics export."""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

import deadlines
from deadlines import RuleError, compute_deadlines, parse_rules

SEED_RULES = deadlines.DEFAULT_RULES
D = dt.date.fromisoformat


def rules(*items, holidays=()):
    return parse_rules({"holidays": list(holidays), "rules": list(items)})


def fixed(rule_id, month, day, year_offset=None):
    params = {"month": month, "day": day}
    if year_offset is not None:
        params["year_offset"] = year_offset
    return {"id": rule_id, "event": rule_id.title(), "type": "fixed_date", "params": params}


def seed_ruleset():
    return deadlines.load_rules(SEED_RULES)


def seed(notice: str, year: int = 2027, **inputs):
    """Every rule the seed file can compute, keyed by rule id."""
    given = {name: D(value) for name, value in inputs.items()}
    return {d.id: d for d in compute_deadlines(seed_ruleset(), D(notice), year, given)}


def planned(notice: str, rule_id: str, year: int = 2027, **inputs):
    return seed(notice, year, **inputs)[rule_id].date.isoformat()


# --- the shipped rules file ---------------------------------------------------

def test_every_shipped_rule_has_a_statute_a_note_and_a_unique_id():
    data = json.loads(Path(SEED_RULES).read_text(encoding="utf-8"))
    ids = [rule["id"] for rule in data["rules"]]
    assert len(ids) == len(set(ids)) >= 30
    assert all(rule["statute"] and rule["note"] and rule["event"] for rule in data["rules"])


def test_core_rules_without_hearing_or_order_dates():
    core = [d.id for d in compute_deadlines(seed_ruleset(), D("2027-04-01"), 2027, include_reference=False)]
    assert core == ["exemption_application_deadline", "protest_deadline", "protest_late_good_cause",
                    "delinquency_date"]


def test_hearing_and_order_rules_wait_for_their_dates():
    assert "hearing_notice_from_arb" not in seed("2027-04-01")
    assert "court_petition" not in seed("2027-04-01")
    assert "hearing_notice_from_arb" in seed("2027-04-01", hearing_date="2027-06-15")
    assert "court_petition" in seed("2027-04-01", arb_order_date="2027-07-20")
    assert "court_petition" not in seed("2027-04-01", hearing_date="2027-06-15")


def test_core_rules_grow_when_dates_are_supplied():
    core = [d.id for d in compute_deadlines(
        seed_ruleset(), D("2027-04-01"), 2027, {"hearing_date": D("2027-06-15"), "arb_order_date": D("2027-07-20")},
        include_reference=False)]
    assert {"hearing_notice_from_arb", "cad_evidence_delivery_if_requested", "owner_request_cad_evidence",
            "exchange_written_materials", "rba_request", "court_petition"} <= set(core)
    assert "soah_deposit" not in core


def test_rules_keep_the_law_agents_cites():
    found = seed("2027-04-01", hearing_date="2027-06-15", arb_order_date="2027-07-20")
    assert found["protest_deadline"].statute == "Tax Code §41.44(a)(1); §1.06; §1.07(c); §1.08"
    assert found["exemption_application_deadline"].statute == "Tax Code §11.43(d); §1.06"
    assert found["cad_evidence_delivery_if_requested"].statute == "Tax Code §41.461(a)-(d); §41.67(d)"
    assert found["court_petition"].statute == "Tax Code §42.21(a); §42.06(a)"
    assert found["soah_notice_of_appeal"].statute == "Gov't Code §2003.901, §2003.906(a-1)"


# --- protest deadline, the worked 2027 examples -------------------------------

@pytest.mark.parametrize("notice, statutory, planned_date", [
    ("2027-04-01", "2027-05-15", "2027-05-17"),   # May 15 wins and is a Saturday
    ("2027-04-15", "2027-05-15", "2027-05-17"),   # both options tie on May 15
    ("2027-04-17", "2027-05-17", "2027-05-17"),   # Monday, no roll
    ("2027-04-20", "2027-05-20", "2027-05-20"),   # 30 days wins
    ("2027-05-01", "2027-05-31", "2027-06-01"),   # Memorial Day rolls to Tuesday
    ("2027-04-30", "2027-05-30", "2027-06-01"),   # Sunday, then Memorial Day
])
def test_protest_deadline_for_2027(notice, statutory, planned_date):
    result = seed(notice)["protest_deadline"]
    assert result.computed_date.isoformat() == statutory
    assert result.date.isoformat() == planned_date


def test_protest_deadline_shows_why_it_moved():
    saturday = seed("2027-04-01")["protest_deadline"]
    assert saturday.roll == "forward" and saturday.roll_reasons == ("Saturday",)
    assert "Statutory date: Sat, May 15, 2027 (Saturday)" in saturday.roll_text
    assert "moves to the next business day, Mon, May 17, 2027" in saturday.roll_text
    holiday = seed("2027-05-01")["protest_deadline"]
    assert holiday.roll_reasons == ("Memorial Day",)
    sunday_then_holiday = seed("2027-04-30")["protest_deadline"]
    assert sunday_then_holiday.roll_reasons == ("Sunday", "Memorial Day")


def test_protest_deadline_without_a_weekend_is_not_rolled():
    result = seed("2026-04-15", 2026)["protest_deadline"]   # May 15, 2026 is a Friday
    assert result.date == result.computed_date == D("2026-05-15")
    assert result.roll == "" and result.roll_text == ""


def test_full_note_combines_the_rule_note_and_the_roll_explanation():
    result = seed("2027-04-01")["protest_deadline"]
    assert result.full_note.startswith(result.note)
    assert result.roll_text in result.full_note and result.full_note.endswith(result.portal_text)


# --- exemption and late-filing dates ----------------------------------------------

def test_exemption_dates_for_2027():
    assert planned("2027-04-01", "exemption_application_deadline") == "2027-04-30"   # a Friday
    assert planned("2027-04-01", "delinquency_date") == "2028-02-01"
    assert planned("2027-04-01", "exemption_late_homestead") == "2030-02-01"
    assert planned("2027-04-01", "exemption_late_disabled_veteran") == "2033-02-01"
    assert planned("2027-04-01", "protest_late_good_cause") == "2027-07-20"


def test_exemption_application_deadline_rolls_when_april_30_is_a_weekend():
    result = seed("2026-04-01", 2026)["exemption_application_deadline"]   # April 30, 2026 is a Thursday
    assert result.date == D("2026-04-30")
    result = seed("2028-04-01", 2028)["exemption_application_deadline"]   # April 30, 2028 is a Sunday
    assert result.date == D("2028-05-01") and result.roll_reasons == ("Sunday",)


def test_before_delinquency_rules_use_the_last_safe_day():
    for rule_id in ("protest_late_no_notice", "motion_to_correct_overappraisal", "court_prepayment"):
        assert planned("2027-04-01", rule_id) == "2028-01-31"


def test_notice_targets():
    assert planned("2027-04-01", "notice_of_value_target_homestead") == "2027-04-01"
    assert planned("2027-04-01", "notice_of_value_target_other") == "2027-05-01"


# --- relative to the hearing and the ARB order ---------------------------------------

def test_dates_counted_back_from_a_june_15_hearing():
    found = seed("2027-04-01", hearing_date="2027-06-15")
    assert found["cad_evidence_notice"].date == D("2027-06-01")
    assert found["owner_certified_appraisal"].date == D("2027-06-01")
    assert found["owner_request_cad_evidence"].date == D("2027-05-25")
    assert found["remote_hearing_request_no_agent"].date == D("2027-06-10")
    assert found["exchange_written_materials"].date == D("2027-06-15")
    assert found["missed_hearing_new_hearing"].computed_date == D("2027-06-19")


def test_back_counted_saturday_dates_show_both_days():
    found = seed("2027-04-01", hearing_date="2027-06-15")
    for rule_id in ("hearing_procedures_copy_if_requested", "single_member_panel_request"):
        assert found[rule_id].computed_date == D("2027-06-05")
        assert found[rule_id].date == D("2027-06-04")
        assert found[rule_id].roll == "back"
        assert "Act by the previous business day, Fri, June 4, 2027" in found[rule_id].roll_text


def test_a_holiday_statutory_day_moves_back_to_the_friday():
    notice = seed("2027-04-01", hearing_date="2027-06-15")["hearing_notice_from_arb"]   # 15 days back is Memorial Day
    assert notice.computed_date == D("2027-05-31") and notice.date == D("2027-05-28")
    assert notice.roll_reasons == ("Memorial Day",)


def test_appeal_windows_for_an_order_received_july_20():
    found = seed("2027-04-01", arb_order_date="2027-07-20")
    assert found["soah_notice_of_appeal"].date == D("2027-08-19")
    assert found["soah_deposit"].date == D("2027-10-18")
    for rule_id in ("court_petition", "rba_request"):
        assert found[rule_id].computed_date == D("2027-09-18")        # a Saturday
        assert found[rule_id].date == D("2027-09-17")


def test_postponement_window():
    found = seed("2027-04-01", hearing_date="2027-06-15")
    assert found["postponement_window_start"].date == D("2027-06-20")
    assert found["postponement_window_end"].date == D("2027-07-15")


# --- engine: holidays, skipping, years --------------------------------------------------

def test_memorial_day_is_the_last_monday_of_may_in_any_year():
    holiday = next(h for h in seed_ruleset().holidays if h.name == "Memorial Day")
    assert [d for d in (D("2026-05-25"), D("2027-05-31"), D("2028-05-29"), D("2029-05-28")) if holiday.falls_on(d)]
    assert not holiday.falls_on(D("2027-05-24"))   # second-to-last Monday
    assert not holiday.falls_on(D("2027-06-07"))


def test_nth_weekday_and_fixed_holidays():
    ruleset = rules({"id": "d", "event": "D", "type": "days_after_notice", "params": {"days": 0},
                     "weekend_roll": True},
                    holidays=[{"name": "Third Monday", "type": "nth_weekday", "month": 6, "weekday": "monday", "n": 3},
                              {"name": "Day Off", "type": "fixed", "date": "2027-06-22"}])
    third_monday = compute_deadlines(ruleset, D("2027-06-21"), 2027)[0]       # June 21, 2027 is the third Monday
    assert third_monday.date == D("2027-06-23")            # Monday holiday, then the fixed Tuesday holiday
    assert third_monday.roll_reasons == ("Third Monday", "Day Off")
    assert compute_deadlines(ruleset, D("2027-06-14"), 2027)[0].date == D("2027-06-14")
    chained = compute_deadlines(ruleset, D("2027-06-22"), 2027)[0]             # fixed holiday Tuesday -> Wednesday
    assert chained.date == D("2027-06-23") and chained.roll_reasons == ("Day Off",)


@pytest.mark.parametrize("holiday", [
    {"name": "X", "type": "nth_weekday", "month": 13, "weekday": "monday", "n": 1},
    {"name": "X", "type": "nth_weekday", "month": 5, "weekday": "someday", "n": 1},
    {"name": "X", "type": "nth_weekday", "month": 5, "weekday": "monday", "n": 5},
    {"name": "X", "type": "fixed", "date": "May 31"},
    {"name": "X", "type": "lunar"},
    {"type": "fixed", "date": "2027-05-31"},
])
def test_bad_holiday_definitions_rejected(holiday):
    with pytest.raises(RuleError, match="holidays"):
        parse_rules({"holidays": [holiday], "rules": []})


def test_years_after_event_handles_feb_29():
    ruleset = rules(fixed("leap", 2, 29),
                    {"id": "later", "event": "Later", "type": "years_after_event",
                     "params": {"event": "leap", "years": 1}},
                    {"id": "later4", "event": "Later4", "type": "years_after_event",
                     "params": {"event": "leap", "years": 4}})
    by_id = {d.id: d.date for d in compute_deadlines(ruleset, D("2028-01-10"), 2028)}
    assert by_id["later"] == D("2029-02-28")      # no Feb 29 in 2029: the earlier day
    assert by_id["later4"] == D("2032-02-29")


def test_rules_that_need_a_missing_input_are_skipped_not_errors():
    ruleset = rules(
        {"id": "h", "event": "H", "type": "days_after_input", "params": {"input": "hearing_date", "days": -14}},
        {"id": "after_h", "event": "After H", "type": "days_after_event", "params": {"event": "h", "days": 3}},
        fixed("plain", 6, 1))
    assert [d.id for d in compute_deadlines(ruleset, D("2027-04-15"), 2027)] == ["plain"]
    both = compute_deadlines(ruleset, D("2027-04-15"), 2027, {"hearing_date": D("2027-06-15")})
    assert [d.id for d in both] == ["h", "plain", "after_h"]


def test_unknown_inputs_and_bad_input_names_are_rejected():
    with pytest.raises(RuleError, match="unknown input"):
        compute_deadlines(rules(fixed("a", 1, 1)), D("2027-04-15"), 2027, {"closing_date": D("2027-06-01")})
    with pytest.raises(RuleError, match="params.input"):
        parse_rules({"rules": [{"id": "x", "event": "X", "type": "days_after_input",
                                "params": {"input": "closing_date", "days": 1}}]})


def test_weekend_roll_and_safe_day_are_mutually_exclusive():
    with pytest.raises(RuleError, match="cannot both be true"):
        parse_rules({"rules": [{**fixed("x", 1, 1), "weekend_roll": True, "safe_day": True}]})


def test_core_flag_filters_the_package_view():
    ruleset = rules(fixed("shown", 5, 1), {**fixed("hidden", 6, 1), "core": False})
    assert [d.id for d in compute_deadlines(ruleset, D("2027-04-15"), 2027, include_reference=False)] == ["shown"]
    assert len(compute_deadlines(ruleset, D("2027-04-15"), 2027)) == 2


# --- engine -----------------------------------------------------------------

def test_listed_holidays_are_skipped_when_rolling():
    ruleset = rules(
        {"id": "d", "event": "D", "type": "days_after_notice", "params": {"days": 30}, "weekend_roll": True},
        holidays=["2027-05-31"])
    # May 30 (Sunday) -> May 31 is a listed holiday -> June 1
    assert compute_deadlines(ruleset, D("2027-04-30"), 2027)[0].date == D("2027-06-01")


def test_no_roll_unless_requested():
    ruleset = rules({"id": "d", "event": "D", "type": "days_after_notice", "params": {"days": 30}})
    result = compute_deadlines(ruleset, D("2027-04-30"), 2027)[0]
    assert result.date == D("2027-05-30") and not result.rolled


def test_leap_day_is_a_valid_fixed_date_only_in_leap_years():
    ruleset = rules(fixed("leap", 2, 29))
    assert compute_deadlines(ruleset, D("2028-01-10"), 2028)[0].date == D("2028-02-29")
    with pytest.raises(RuleError, match="does not exist in 2027"):
        compute_deadlines(ruleset, D("2027-01-10"), 2027)


def test_day_counts_cross_february_correctly():
    ruleset = rules({"id": "d", "event": "D", "type": "days_after_notice", "params": {"days": 30}})
    assert compute_deadlines(ruleset, D("2028-02-01"), 2028)[0].date == D("2028-03-02")  # leap year
    assert compute_deadlines(ruleset, D("2027-02-01"), 2027)[0].date == D("2027-03-03")


def test_year_offset_moves_fixed_dates_to_other_years():
    ruleset = rules(fixed("next", 1, 31, year_offset=1))
    assert compute_deadlines(ruleset, D("2027-04-15"), 2027)[0].date == D("2028-01-31")


def test_days_after_event_chains_from_the_final_date_of_the_other_rule():
    ruleset = rules(
        {"id": "filing", "event": "Filing", "type": "fixed_date", "params": {"month": 5, "day": 15},
         "weekend_roll": True},
        {"id": "evidence", "event": "Evidence", "type": "days_after_event",
         "params": {"event": "filing", "days": 14}},
    )
    by_id = {d.id: d for d in compute_deadlines(ruleset, D("2027-04-15"), 2027)}
    assert by_id["filing"].date == D("2027-05-17")           # May 15, 2027 is a Saturday
    assert by_id["evidence"].date == D("2027-05-31")          # counted from the rolled date


def test_events_can_be_defined_in_any_order():
    ruleset = rules(
        {"id": "late", "event": "Late", "type": "days_after_event", "params": {"event": "early", "days": 5}},
        fixed("early", 6, 1),
    )
    assert [d.id for d in compute_deadlines(ruleset, D("2027-04-15"), 2027)] == ["early", "late"]


def test_results_sorted_by_date():
    ruleset = rules(fixed("b", 9, 1), fixed("a", 3, 1))
    assert [d.id for d in compute_deadlines(ruleset, D("2027-04-15"), 2027)] == ["a", "b"]


def test_earlier_of_and_nested_later_of():
    ruleset = rules(
        {"id": "e", "event": "E", "type": "earlier_of", "params": {"options": [
            {"type": "fixed_date", "params": {"month": 5, "day": 15}},
            {"type": "days_after_notice", "params": {"days": 90}}]}},
        {"id": "n", "event": "N", "type": "later_of", "params": {"options": [
            {"type": "fixed_date", "params": {"month": 1, "day": 1}},
            {"type": "later_of", "params": {"options": [
                {"type": "days_after_notice", "params": {"days": 1}},
                {"type": "days_after_notice", "params": {"days": 2}}]}}]}},
    )
    by_id = {d.id: d.date for d in compute_deadlines(ruleset, D("2027-04-15"), 2027)}
    assert by_id["e"] == D("2027-05-15")
    assert by_id["n"] == D("2027-04-17")


@pytest.mark.parametrize("bad, message", [
    ({"id": "x", "event": "X", "type": "someday", "params": {}}, "type: must be one of"),
    ({"id": "x", "event": "X", "type": "fixed_date", "params": {"month": 13, "day": 1}}, "params.month"),
    ({"id": "x", "event": "X", "type": "fixed_date", "params": {"month": 5}}, "params.day: required"),
    ({"id": "x", "event": "X", "type": "days_after_notice"}, "params: required object"),
    ({"id": "x", "event": "X", "type": "days_after_notice", "params": {"days": "30"}}, "params.days"),
    ({"id": "x", "event": "X", "type": "later_of", "params": {"options": [
        {"type": "days_after_notice", "params": {"days": 1}}]}}, "at least two"),
    ({"id": "x", "event": "X", "type": "days_after_event", "params": {"event": "nope", "days": 1}},
     "unknown rule id 'nope'"),
    ({"event": "no id", "type": "fixed_date", "params": {"month": 1, "day": 1}}, "rules[0].id"),
    ({"id": "x", "event": "X", "type": "fixed_date", "params": {"month": 1, "day": 1}, "weekend_roll": "yes"},
     "weekend_roll"),
])
def test_malformed_rules_are_rejected_with_a_clear_message(bad, message):
    with pytest.raises(RuleError, match=re.escape(message)):
        parse_rules({"rules": [bad]})


def test_duplicate_ids_rejected():
    with pytest.raises(RuleError, match="duplicate id 'a'"):
        parse_rules({"rules": [fixed("a", 1, 1), fixed("a", 2, 2)]})


def test_circular_references_detected():
    with pytest.raises(RuleError, match="circular rule reference: a -> b -> a"):
        rules(
            {"id": "a", "event": "A", "type": "days_after_event", "params": {"event": "b", "days": 1}},
            {"id": "b", "event": "B", "type": "days_after_event", "params": {"event": "a", "days": 1}},
        )


def test_a_rule_counted_from_itself_is_rejected_at_load():
    with pytest.raises(RuleError, match="circular rule reference: a -> a"):
        rules({"id": "a", "event": "A", "type": "days_after_event", "params": {"event": "a", "days": 1}})


def test_cycles_hidden_inside_nested_specs_are_rejected_at_load():
    nested = {"type": "later_of", "params": {"options": [
        {"type": "fixed_date", "params": {"month": 5, "day": 1}},
        {"type": "days_after_event", "params": {"event": "b", "days": 1}}]}}
    with pytest.raises(RuleError, match="circular rule reference"):
        rules({"id": "a", "event": "A", **nested},
              {"id": "b", "event": "B", "type": "years_after_event", "params": {"event": "a", "years": 1}})


def test_rules_file_must_be_an_object_with_rules():
    with pytest.raises(RuleError, match='"rules" list'):
        parse_rules([])


def test_bad_holiday_rejected():
    with pytest.raises(RuleError, match="holidays"):
        parse_rules({"holidays": ["May 31"], "rules": []})


# --- iCalendar --------------------------------------------------------------

STAMP = dt.datetime(2027, 4, 20, 12, 30, 5, tzinfo=dt.timezone.utc)


def build(items=None, tax_year=2027):
    if items is None:
        everything = compute_deadlines(deadlines.load_rules(SEED_RULES), D("2027-04-15"), tax_year)
        items = [d for d in everything if d.id == "protest_deadline"]
    return deadlines.build_ics(items, tax_year, STAMP)


def unfold(text: str):
    return text.replace("\r\n ", "").split("\r\n")


def test_ics_uses_crlf_and_balanced_blocks():
    text = build()
    assert text.endswith("\r\n")
    assert "\n" not in text.replace("\r\n", "")
    lines = unfold(text)[:-1]
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-1] == "END:VCALENDAR"
    stack = []
    for line in lines:
        if line.startswith("BEGIN:"):
            stack.append(line[6:])
        elif line.startswith("END:"):
            assert stack.pop() == line[4:]
    assert stack == []


def test_ics_required_properties():
    lines = unfold(build())
    assert "VERSION:2.0" in lines
    assert any(line.startswith("PRODID:") for line in lines)
    assert "DTSTAMP:20270420T123005Z" in lines
    assert any(re.fullmatch(r"UID:[0-9a-f-]{36}@tx-property-tax-protest", line) for line in lines)


def test_ics_event_is_all_day_with_exclusive_end():
    lines = unfold(build())
    assert "DTSTART;VALUE=DATE:20270517" in lines
    assert "DTEND;VALUE=DATE:20270518" in lines
    assert "SUMMARY:Protest filing deadline" in lines


def test_ics_event_at_month_end_ends_on_first_of_next_month():
    item = deadlines.Deadline("x", "End of month", D("2027-05-31"), D("2027-05-31"), "", "")
    assert "DTEND;VALUE=DATE:20270601" in unfold(build([item]))


def test_ics_has_reminders_14_and_3_days_before():
    lines = unfold(build())
    assert lines.count("BEGIN:VALARM") == 2
    assert "TRIGGER:-P14D" in lines and "TRIGGER:-P3D" in lines
    assert lines.count("ACTION:DISPLAY") == 2


def test_ics_uids_are_stable_and_unique():
    first = [line for line in unfold(build()) if line.startswith("UID:")]
    again = [line for line in unfold(build()) if line.startswith("UID:")]
    assert first == again
    items = [deadlines.Deadline(i, i, D("2027-05-17"), D("2027-05-17"), "", "") for i in ("a", "b", "c")]
    uids = [line for line in unfold(build(items)) if line.startswith("UID:")]
    assert len(set(uids)) == 3


def test_ics_text_is_escaped():
    item = deadlines.Deadline("x", "Hearing, informal; bring copies", D("2027-06-01"), D("2027-06-01"),
                              "", "Line one\nLine two")
    lines = unfold(build([item]))
    assert "SUMMARY:Hearing\\, informal\\; bring copies" in lines
    assert "DESCRIPTION:Line one\\nLine two" in lines


def test_ics_folds_long_lines_to_75_octets_without_splitting_characters():
    note = "Section § 41.44 " * 20
    item = deadlines.Deadline("x", "Long", D("2027-06-01"), D("2027-06-01"), "", note)
    text = build([item])
    for physical in text.split("\r\n"):
        assert len(physical.encode("utf-8")) <= 75
    description = [line for line in unfold(text) if line.startswith("DESCRIPTION:Section")][0]
    assert description == "DESCRIPTION:" + note


def test_ics_mentions_rolled_date():
    text = "\n".join(unfold(build()))
    assert r"Statutory date: Sat\, May 15\, 2027 (Saturday)" in text   # commas are escaped in iCalendar text


# --- command line -----------------------------------------------------------

def test_cli_prints_deadlines_and_writes_ics(tmp_path, capsys):
    target = tmp_path / "out.ics"
    code = deadlines.main(["--notice-date", "2027-04-15", "--tax-year", "2027", "--ics", str(target),
                           "--dtstamp", "2027-04-20T12:30:05+00:00"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Mon 2027-05-17  Protest filing deadline" in out
    assert "Roll:  Statutory date: Sat, May 15, 2027 (Saturday)." in out
    assert "more reference date(s) not shown; add --all" in out
    raw = target.read_bytes()
    assert b"\r\n" in raw and b"DTSTAMP:20270420T123005Z" in raw


def test_cli_json_matches_case_json_deadline_shape(capsys):
    assert deadlines.main(["--notice-date", "2027-04-20", "--tax-year", "2027", "--json"]) == 0
    items = {entry["event"]: entry for entry in json.loads(capsys.readouterr().out)}
    item = items["Protest filing deadline"]
    assert item["event"] == "Protest filing deadline" and item["date"] == "2027-05-20"
    assert set(item) <= {"event", "date", "statute", "note"}


def test_cli_custom_rules_file(tmp_path, capsys):
    path = tmp_path / "rules.json"
    path.write_text(json.dumps({"rules": [fixed("hearing", 6, 1)]}), encoding="utf-8")
    assert deadlines.main(["--notice-date", "2027-04-15", "--tax-year", "2027", "--rules", str(path)]) == 0
    assert "2027-06-01  Hearing" in capsys.readouterr().out


def test_cli_reports_bad_rules_with_exit_code_2(tmp_path, capsys):
    path = tmp_path / "rules.json"
    path.write_text("{}", encoding="utf-8")
    assert deadlines.main(["--notice-date", "2027-04-15", "--tax-year", "2027", "--rules", str(path)]) == 2
    assert "error:" in capsys.readouterr().err
    assert deadlines.main(["--notice-date", "2027-04-15", "--tax-year", "2027", "--rules", str(tmp_path / "x")]) == 2


def test_cli_hearing_and_order_dates_add_relative_events(capsys):
    code = deadlines.main(["--notice-date", "2027-04-01", "--tax-year", "2027", "--hearing-date", "2027-06-15",
                           "--arb-order-date", "2027-07-20"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Fri 2027-05-28  ARB mails the hearing notice by" in out
    assert "Statutory date: Mon, May 31, 2027 (Memorial Day). Act by the previous business day, Fri, May 28, 2027" in out
    assert "Fri 2027-09-17  File a court petition for review by" in out
    assert "Statutory date: Sat, September 18, 2027 (Saturday)" in out


def test_cli_all_lists_reference_dates(capsys):
    deadlines.main(["--notice-date", "2027-04-01", "--tax-year", "2027"])
    core_only = capsys.readouterr().out
    deadlines.main(["--notice-date", "2027-04-01", "--tax-year", "2027", "--all"])
    everything = capsys.readouterr().out
    assert "Last day to file a late homestead exemption" not in core_only
    assert "Fri 2030-02-01  Last day to file a late homestead exemption" in everything
    assert "not shown" not in everything


def test_cli_ics_includes_hearing_events_when_supplied(tmp_path):
    target = tmp_path / "out.ics"
    deadlines.main(["--notice-date", "2027-04-01", "--tax-year", "2027", "--hearing-date", "2027-06-15",
                    "--ics", str(target), "--dtstamp", "2027-04-20T00:00:00+00:00"])
    text = target.read_bytes().decode("utf-8")
    assert "SUMMARY:ARB mails the hearing notice by" in text
    assert "DTSTART;VALUE=DATE:20270528" in text
