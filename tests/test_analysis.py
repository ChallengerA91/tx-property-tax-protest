"""Medians, comp adjustments, unequal-appraisal ranking and income math."""
from __future__ import annotations

import pytest

from analysis import build_analysis, build_comp_rows, build_income, build_unequal, mean, median, per_sqft
from case_schema import load_case


def test_median_odd_count():
    assert median([5, 1, 3]) == 3


def test_median_even_count_averages_middle_pair():
    assert median([4, 1, 3, 2]) == 2.5


def test_median_ignores_missing_values():
    assert median([None, 10, None, 20, 30]) == 20


def test_median_ignores_booleans_and_text():
    assert median([True, "x", 4, 8]) == 6


def test_median_of_nothing_is_none():
    assert median([]) is None
    assert median([None, None]) is None


def test_median_single_value():
    assert median([7]) == 7


def test_mean_ignores_missing_values():
    assert mean([None, 10, 20]) == 15
    assert mean([]) is None


def test_per_sqft_handles_missing_and_zero():
    assert per_sqft(200000, 2000) == 100
    assert per_sqft(None, 2000) is None
    assert per_sqft(200000, None) is None
    assert per_sqft(200000, 0) is None


def test_comp_adjustments_add_to_price():
    rows = build_comp_rows([{
        "address": "1 A St", "price": 400000, "sqft": 2000,
        "adjustments": [{"label": "pool", "amount": -15000}, {"label": "size", "amount": 5000}],
    }])
    row = rows[0]
    assert row.adjustment_total == -10000
    assert row.adjusted_value == 390000
    assert row.price_ppsf == 200
    assert row.adjusted_ppsf == 195
    assert row.price_type == "sale"


def test_comp_without_sqft_has_no_ppsf_and_is_skipped_in_ppsf_median():
    rows = build_comp_rows([
        {"address": "1 A", "price": 300000, "sqft": 1500},
        {"address": "2 B", "price": 900000},
        {"address": "3 C", "price": 400000, "sqft": 2000},
    ])
    assert rows[1].price_ppsf is None
    assert median(r.price_ppsf for r in rows) == 200  # (200 + 200) / 2, the $900k comp is ignored


def neighbors(*pairs):
    return [{"address": f"N{i}", "appraised_value": value, "sqft": sqft} for i, (value, sqft) in enumerate(pairs)]


def test_unequal_rank_and_percentile():
    # $/sqft: 100, 110, 120, 130; subject at 125 sits above three and below one
    u = build_unequal(neighbors((100, 1), (110, 1), (120, 1), (130, 1)), subject_sqft=1, subject_value=125)
    assert u.rank == 2 and u.group_size == 5
    assert u.percentile == 75
    assert u.median_ppsf == 115
    assert u.indicated_value == 115
    assert [n.ppsf for n in u.neighbors] == [130, 120, 110, 100]


def test_unequal_ties_count_half_in_percentile():
    u = build_unequal(neighbors((100, 1), (125, 1), (150, 1)), subject_sqft=1, subject_value=125)
    assert u.rank == 2
    assert u.percentile == pytest.approx(50.0)


def test_unequal_highest_subject_ranks_first():
    u = build_unequal(neighbors((100, 1), (110, 1)), subject_sqft=1, subject_value=500)
    assert u.rank == 1 and u.percentile == 100


def test_unequal_ignores_neighbors_without_sqft():
    data = neighbors((100, 1), (120, 1))
    data.append({"address": "no size", "appraised_value": 999999})
    u = build_unequal(data, subject_sqft=1, subject_value=110)
    assert len(u.neighbors) == 2


def test_unequal_none_when_no_usable_neighbors():
    assert build_unequal([{"address": "x", "appraised_value": 1}], 1, 1) is None
    assert build_unequal([], 1, 1) is None


def test_income_math():
    inc = build_income({
        "gross_rent": 24000, "vacancy_pct": 5,
        "expenses": [{"label": "ins", "amount": 1000}, {"label": "repairs", "amount": 2000}],
        "cap_rate_pct": 8, "cap_rate_source": "survey",
    })
    assert inc.vacancy_loss == 1200
    assert inc.effective_gross_income == 22800
    assert inc.total_expenses == 3000
    assert inc.noi == 19800
    assert inc.indicated_value == pytest.approx(247500)


def test_sample_homestead_analysis(write_case, homestead_case):
    a = build_analysis(load_case(write_case(homestead_case)))
    assert len(a.sale_comps) == 5 and len(a.other_comps) == 1      # the unsold listing is not in the median
    assert a.median_adjusted == 421000  # odd count of 5 sales
    assert a.mean_adjusted == pytest.approx(421180)
    assert a.reduction == 40000
    assert a.reduction_pct == pytest.approx(40000 / 465000 * 100)
    assert a.unequal.rank == 2 and a.unequal.group_size == 9
    assert a.unequal.percentile == pytest.approx(87.5)
    assert a.income is None


def test_sample_rental_analysis(write_case, rental_case):
    a = build_analysis(load_case(write_case(rental_case)))
    assert a.median_adjusted == 290000  # odd count of 5
    assert a.income.noi == pytest.approx(18696)
    assert a.income.indicated_value == pytest.approx(18696 / 0.07)


def test_deadlines_in_case_are_used_verbatim(write_case, rental_case):
    rental_case["deadlines"] = [
        {"event": "Protest filing deadline", "date": "2027-05-17", "statute": "Tax Code 41.44"},
        {"event": "Prepare the packet", "date": "2027-06-01", "note": "Own milestone."},
    ]
    a = build_analysis(load_case(write_case(rental_case)))
    assert [d.event for d in a.deadlines] == ["Protest filing deadline", "Prepare the packet"]
    assert a.deadlines[0].date.isoformat() == "2027-05-17" and a.deadlines[1].full_note == "Own milestone."


def test_deadlines_computed_from_notice_date_when_absent(write_case, homestead_case):
    a = build_analysis(load_case(write_case(homestead_case)))
    assert [(d.id, d.date.isoformat()) for d in a.deadlines] == [
        ("exemption_application_deadline", "2027-04-30"),
        ("protest_deadline", "2027-05-17"),
        ("protest_late_good_cause", "2027-07-20"),
        ("delinquency_date", "2028-02-01"),
    ]


def test_rental_sample_uses_the_30_day_branch(write_case, rental_case):
    a = build_analysis(load_case(write_case(rental_case)))
    protest = next(d for d in a.deadlines if d.id == "protest_deadline")
    assert protest.date.isoformat() == "2027-05-24" and not protest.rolled   # notice 2027-04-24 + 30 days


def test_hearing_and_order_dates_in_the_case_add_deadlines(write_case, homestead_case):
    homestead_case["hearing_date"] = "2027-06-15"
    homestead_case["arb_order_date"] = "2027-07-20"
    a = build_analysis(load_case(write_case(homestead_case)))
    found = {d.id: d for d in a.deadlines}
    assert found["hearing_notice_from_arb"].date.isoformat() == "2027-05-28"
    assert found["court_petition"].date.isoformat() == "2027-09-17"
    assert "soah_deposit" not in found          # reference dates stay out of the package


# --- capped homesteads ---------------------------------------------------------------------

def test_capped_analysis_separates_market_and_appraised_value(write_case, capped_case):
    a = build_analysis(load_case(write_case(capped_case)))
    assert (a.market_value, a.appraised_value, a.argued_value) == (520000, 462000, 470000)
    assert a.capped and a.value_term == "market value"
    assert a.reduction == 50000                                    # market - argued
    assert a.reduction_pct == pytest.approx(50000 / 520000 * 100)
    assert a.market_ppsf == pytest.approx(520000 / 2400)
    assert a.savings.protest_blocked and a.savings.reduction == 0


def test_omitting_market_value_changes_nothing(write_case, homestead_case):
    without = build_analysis(load_case(write_case(homestead_case)))
    homestead_case["subject"]["market_value"] = homestead_case["subject"]["appraised_value"]
    explicit = build_analysis(load_case(write_case(homestead_case, "explicit.json")))
    assert without.market_value == without.appraised_value == 465000
    assert not without.capped and without.value_term == "appraised value"
    for field in ("reduction", "reduction_pct", "market_ppsf", "median_adjusted"):
        assert getattr(without, field) == getattr(explicit, field)
    assert without.savings == explicit.savings
    assert without.reduction == 40000


def test_unequal_comparison_uses_the_market_value_of_a_capped_homestead(write_case, capped_case):
    capped_case["strategy"] = "both"
    capped_case["legal_basis"]["unequal_cite"] = "Tax Code §41.41(a)(2)"
    capped_case["neighbors"] = [{"address": "N1", "appraised_value": 500000, "sqft": 2400},
                                {"address": "N2", "appraised_value": 480000, "sqft": 2400}]
    a = build_analysis(load_case(write_case(capped_case)))
    assert a.unequal.subject_ppsf == pytest.approx(520000 / 2400)  # not 462,000 / 2,400
    assert a.unequal.rank == 1
