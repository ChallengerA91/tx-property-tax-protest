"""case.json validation: every problem is reported, with the field path and what is wrong."""
from __future__ import annotations

from pathlib import Path

import pytest

from case_schema import CASE_FIELDS, CaseError, drop_nulls, load_case, validate_case

SCHEMA_DOC = (Path(__file__).resolve().parent.parent
              / "skills" / "tx-property-tax-protest" / "references" / "case-schema.md")


def has_error(errors, fragment):
    return any(fragment in error for error in errors)


def test_both_samples_are_valid(homestead_case, rental_case):
    assert validate_case(homestead_case) == []
    assert validate_case(rental_case) == []


def test_missing_required_field_is_named(homestead_case):
    del homestead_case["subject"]["sqft"]
    assert "subject.sqft: required field is missing" in validate_case(homestead_case)


def test_missing_top_level_blocks_are_all_reported_at_once(homestead_case):
    for key in ("owner", "cad", "tax_rates", "argued_value"):
        del homestead_case[key]
    errors = validate_case(homestead_case)
    for key in ("owner", "cad", "tax_rates", "argued_value"):
        assert f"{key}: required field is missing" in errors


def test_wrong_type_message_shows_the_value(homestead_case):
    homestead_case["subject"]["sqft"] = "big"
    assert "subject.sqft: must be a number (got 'big')" in validate_case(homestead_case)


def test_booleans_are_not_numbers(homestead_case):
    homestead_case["argued_value"] = True
    assert has_error(validate_case(homestead_case), "argued_value: must be a number")


def test_non_positive_numbers_rejected(homestead_case):
    homestead_case["subject"]["sqft"] = 0
    homestead_case["tax_rates"]["total"] = -1
    errors = validate_case(homestead_case)
    assert has_error(errors, "subject.sqft: must be greater than 0")
    assert has_error(errors, "tax_rates.total: must be greater than 0")


def test_list_items_report_their_index(homestead_case):
    del homestead_case["comps"][2]["price"]
    homestead_case["neighbors"][1]["appraised_value"] = "n/a"
    errors = validate_case(homestead_case)
    assert "comps[2].price: required field is missing" in errors
    assert has_error(errors, "neighbors[1].appraised_value: must be a number")


def test_unknown_field_suggests_the_right_name(homestead_case):
    homestead_case["subject"]["apraised_value"] = 1
    errors = validate_case(homestead_case)
    assert has_error(errors, "subject.apraised_value: unknown field (did you mean 'appraised_value'?)")


def test_underscore_keys_are_free_form_notes(homestead_case):
    homestead_case["_scratch"] = "anything"
    homestead_case["comps"][0]["_why"] = "closest sale"
    assert validate_case(homestead_case) == []


def test_bad_date_format(homestead_case):
    homestead_case["notice_date"] = "04/15/2027"
    assert has_error(validate_case(homestead_case), "notice_date: must be a date written YYYY-MM-DD")


def test_impossible_date(homestead_case):
    homestead_case["subject"]["purchase_date"] = "2027-02-30"
    assert has_error(validate_case(homestead_case), "subject.purchase_date: must be a date")


def test_path_must_be_known(homestead_case):
    homestead_case["path"] = "commercial"
    assert has_error(validate_case(homestead_case), "path: must be one of homestead, rental")


def test_rental_income_block_is_optional_when_sales_comps_lead(rental_case):
    del rental_case["income"]
    assert validate_case(rental_case) == []


def test_homestead_rejects_income_block(homestead_case, rental_case):
    homestead_case["income"] = rental_case["income"]
    assert has_error(validate_case(homestead_case), "income: only allowed when path is 'rental'")


def test_income_fields_validated(rental_case):
    rental_case["income"]["cap_rate_pct"] = 0
    rental_case["income"]["vacancy_pct"] = 120
    del rental_case["income"]["cap_rate_source"]
    errors = validate_case(rental_case)
    assert has_error(errors, "income.cap_rate_pct: must be greater than 0")
    assert has_error(errors, "income.vacancy_pct: must be at most 100")
    assert "income.cap_rate_source: required field is missing" in errors


def test_argued_value_must_be_a_reduction(homestead_case):
    homestead_case["argued_value"] = homestead_case["subject"]["appraised_value"]
    assert has_error(validate_case(homestead_case), "argued_value: must be below subject.appraised_value")


def test_market_strategy_needs_its_cite_and_comps(homestead_case):
    homestead_case["strategy"] = "market_value"
    del homestead_case["legal_basis"]["market_value_cite"]
    homestead_case["comps"] = []
    errors = validate_case(homestead_case)
    assert has_error(errors, "legal_basis.market_value_cite: required when strategy is 'market_value'")
    assert has_error(errors, "comps: at least one comparable with price_type 'sale' is required")


def test_unequal_strategy_needs_cite_and_neighbors_with_sqft(homestead_case):
    del homestead_case["legal_basis"]["unequal_cite"]
    homestead_case["neighbors"] = [{"address": "x", "appraised_value": 1}]
    errors = validate_case(homestead_case)
    assert has_error(errors, "legal_basis.unequal_cite: required when strategy is 'both'")
    assert has_error(errors, "neighbors: at least one neighbor with sqft is required")


def test_strategy_defaults_to_market_value(homestead_case):
    del homestead_case["strategy"]
    del homestead_case["legal_basis"]["unequal_cite"]
    homestead_case["neighbors"] = []
    assert validate_case(homestead_case) == []


def test_rental_may_omit_comps(rental_case):
    rental_case["comps"] = []
    assert validate_case(rental_case) == []


def test_eligible_exemption_needs_instructions(homestead_case):
    del homestead_case["exemptions"]["eligible"][0]["how_to_claim"]
    assert has_error(validate_case(homestead_case), "exemptions.eligible[0].how_to_claim: required")


def test_exemption_amount_needs_applies_to(homestead_case):
    del homestead_case["exemptions"]["eligible"][0]["applies_to"]
    errors = validate_case(homestead_case)
    assert has_error(errors, "exemptions.eligible[0].applies_to: required when amount is given")


def test_school_exemption_needs_school_rate(homestead_case):
    del homestead_case["tax_rates"]["school"]
    assert has_error(validate_case(homestead_case), "tax_rates.school: required because exemptions.eligible[0]")


def test_total_exemption_needs_no_amount(homestead_case):
    homestead_case["exemptions"]["eligible"].append(
        {"name": "Full exemption", "kind": "total", "how_to_claim": "Apply with the district."})
    assert validate_case(homestead_case) == []


def test_needs_notice_date_or_deadlines(homestead_case):
    del homestead_case["notice_date"]
    assert has_error(validate_case(homestead_case), "notice_date: provide notice_date")


def test_filing_methods_required(homestead_case):
    homestead_case["filing"]["methods"] = []
    assert has_error(validate_case(homestead_case), "filing.methods: needs at least 1 item(s)")


def test_scenario_fractions_must_be_ordered_and_in_range(homestead_case):
    homestead_case["settlement_scenarios"] = {"low_fraction": 0.9, "high_fraction": 0.4}
    assert has_error(validate_case(homestead_case), "low_fraction (0.9) must not exceed high_fraction (0.4)")
    homestead_case["settlement_scenarios"] = {"low_fraction": 0.5, "high_fraction": 1.5}
    assert has_error(validate_case(homestead_case), "settlement_scenarios.high_fraction: must be at most 1")


def test_top_level_must_be_an_object():
    assert has_error(validate_case([]), "must be an object")


def test_null_counts_as_missing(homestead_case):
    homestead_case["subject"]["sqft"] = None
    assert "subject.sqft: required field is missing" in validate_case(homestead_case)
    assert drop_nulls({"a": None, "b": [{"c": None, "d": 1}]}) == {"b": [{"d": 1}]}


def test_load_case_round_trip(write_case, homestead_case):
    assert load_case(write_case(homestead_case))["path"] == "homestead"


def test_load_case_raises_with_all_errors(write_case, homestead_case):
    del homestead_case["owner"]
    del homestead_case["subject"]["sqft"]
    with pytest.raises(CaseError) as caught:
        load_case(write_case(homestead_case))
    assert len(caught.value.errors) == 2


def test_load_case_reports_bad_json(tmp_path):
    path = tmp_path / "case.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(CaseError) as caught:
        load_case(path)
    assert "not valid JSON" in caught.value.errors[0]


def test_load_case_reports_missing_file(tmp_path):
    with pytest.raises(CaseError) as caught:
        load_case(tmp_path / "nope.json")
    assert "file not found" in caught.value.errors[0]


def test_schema_doc_mentions_every_top_level_field():
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    assert [name for name in CASE_FIELDS if f"`{name}`" not in text] == []


# --- market_value for capped homesteads ------------------------------------------------

def test_capped_sample_is_valid(capped_case):
    assert validate_case(capped_case) == []


def test_market_value_may_not_be_below_the_appraised_value(capped_case):
    capped_case["subject"]["market_value"] = 400000                # appraised is 462,000
    assert has_error(validate_case(capped_case), "subject.market_value: must be at least subject.appraised_value")


def test_market_value_must_be_positive_and_numeric(capped_case):
    capped_case["subject"]["market_value"] = "a lot"
    assert has_error(validate_case(capped_case), "subject.market_value: must be a number")


def test_argued_value_may_sit_between_appraised_and_market_value(capped_case):
    capped_case["argued_value"] = 500000                           # above the 462,000 appraised value
    assert validate_case(capped_case) == []


def test_argued_value_must_be_below_market_value_when_given(capped_case):
    capped_case["argued_value"] = 520000
    errors = validate_case(capped_case)
    assert has_error(errors, "argued_value: must be below subject.market_value (520,000)")
    assert not has_error(errors, "subject.appraised_value")


def test_without_market_value_argued_must_still_be_below_appraised(homestead_case):
    homestead_case["argued_value"] = 465000
    assert has_error(validate_case(homestead_case), "argued_value: must be below subject.appraised_value (465,000)")


def test_market_value_equal_to_appraised_value_is_the_same_as_omitting_it(homestead_case):
    homestead_case["subject"]["market_value"] = homestead_case["subject"]["appraised_value"]
    assert validate_case(homestead_case) == []
