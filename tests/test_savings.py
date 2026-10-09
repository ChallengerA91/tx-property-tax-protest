"""Savings math: protest range, exemptions, caps, rounding, the meter line and the CLI."""
from __future__ import annotations

import json

import pytest

import savings
from fmt import money


def test_protest_savings_default_scenarios():
    result = savings.protest_savings(465000, 425000, 2.15)
    assert result.low == pytest.approx(430.0)   # half of the $40,000 reduction
    assert result.high == pytest.approx(860.0)  # all of it


def test_protest_savings_custom_fractions():
    result = savings.protest_savings(500000, 450000, 2.0, low_fraction=0.25, high_fraction=0.75)
    assert result.low == pytest.approx(250.0)
    assert result.high == pytest.approx(750.0)


def test_no_reduction_means_no_savings():
    assert savings.protest_savings(400000, 400000, 2.0) == savings.SavingsRange(0, 0)
    assert savings.protest_savings(400000, 450000, 2.0) == savings.SavingsRange(0, 0)


@pytest.mark.parametrize("low, high", [(-0.1, 0.5), (0.8, 0.2), (0.5, 1.2)])
def test_invalid_fractions_rejected(low, high):
    with pytest.raises(ValueError, match="fractions must satisfy"):
        savings.protest_savings(400000, 300000, 2.0, low, high)


def test_school_exemption_uses_school_rate():
    items = [{"name": "School break", "amount": 100000, "applies_to": "school"}]
    [priced] = savings.exemption_savings(items, {"total": 2.0, "school": 1.0}, taxable_value=400000)
    assert priced.annual == pytest.approx(1000.0)
    assert priced.quantified


def test_all_exemption_uses_total_rate():
    items = [{"name": "Local", "amount": 25000, "applies_to": "all"}]
    [priced] = savings.exemption_savings(items, {"total": 2.0}, taxable_value=400000)
    assert priced.annual == pytest.approx(500.0)


def test_exemption_cannot_exceed_taxable_value():
    items = [{"name": "Huge", "amount": 900000, "applies_to": "all"}]
    [priced] = savings.exemption_savings(items, {"total": 2.0}, taxable_value=300000)
    assert priced.annual == pytest.approx(6000.0)


def test_total_exemption_removes_the_whole_bill():
    items = [{"name": "Full", "kind": "total"}]
    [priced] = savings.exemption_savings(items, {"total": 2.5}, taxable_value=400000)
    assert priced.annual == pytest.approx(10000.0)
    assert priced.quantified


def test_exemption_without_amount_is_not_quantified():
    [priced] = savings.exemption_savings([{"name": "Freeze"}], {"total": 2.0}, taxable_value=400000)
    assert priced.annual == 0 and not priced.quantified


def test_school_exemption_without_school_rate_is_an_error():
    items = [{"name": "School break", "amount": 100, "applies_to": "school"}]
    with pytest.raises(ValueError, match="tax_rates.school"):
        savings.exemption_savings(items, {"total": 2.0}, taxable_value=1000)


def test_estimate_for_sample_case(homestead_case):
    estimate = savings.estimate_savings(homestead_case)
    assert estimate.reduction == 40000
    assert estimate.protest.low == pytest.approx(430.0)
    assert estimate.protest.high == pytest.approx(860.0)
    assert [e.annual for e in estimate.exemptions] == [pytest.approx(630.0), 0.0]
    assert estimate.total.low == pytest.approx(1060.0)
    assert estimate.total.high == pytest.approx(1490.0)


def test_on_file_exemptions_are_not_counted(homestead_case):
    estimate = savings.estimate_savings(homestead_case)
    assert all(item.name != "School-district residence homestead exemption" for item in estimate.exemptions)


def test_call_arguments_override_case_scenarios(homestead_case):
    estimate = savings.estimate_savings(homestead_case, low_fraction=0.0, high_fraction=0.5)
    assert estimate.protest.low == 0
    assert estimate.protest.high == pytest.approx(430.0)


def test_partial_case_without_argued_value_counts_exemptions_only():
    case = {
        "subject": {"appraised_value": 300000},
        "tax_rates": {"total": 2.0, "school": 1.0},
        "exemptions": {"eligible": [{"name": "School break", "amount": 10000, "applies_to": "school"}]},
    }
    estimate = savings.estimate_savings(case)
    assert estimate.protest == savings.SavingsRange(0, 0)
    assert estimate.total.low == estimate.total.high == pytest.approx(100.0)


def test_estimate_requires_total_rate():
    with pytest.raises(ValueError, match=r"tax_rates.total is required"):
        savings.estimate_savings({"subject": {"appraised_value": 1}})


def test_meter_format_matches_contract():
    assert savings.format_meter(1072.5, 1502.5) == "Estimated savings so far: $1,073 to $1,503 per year"
    assert savings.format_meter(0, 0) == "Estimated savings so far: $0 per year"
    assert savings.format_meter(500, 500) == "Estimated savings so far: $500 per year"


def test_money_rounds_half_up_not_to_even():
    assert money(1072.5) == "$1,073"
    assert money(2.5) == "$3"
    assert money(-1072.5) == "-$1,073"
    assert money(0.4) == "$0"
    assert money(221.425, cents=True) == "$221.43"


def test_scenario_text():
    estimate = savings.estimate_savings({
        "subject": {"appraised_value": 2}, "tax_rates": {"total": 1}, "argued_value": 1,
        "settlement_scenarios": {"low_fraction": 0.125, "high_fraction": 1}})
    assert savings.scenario_text(estimate) == "12.5% and 100% of the argued reduction"


def test_cli_meter_from_flags(capsys):
    code = savings.main(["--appraised", "400000", "--argued", "360000", "--total-rate", "2.1", "--meter"])
    assert code == 0
    assert capsys.readouterr().out.strip() == "Estimated savings so far: $420 to $840 per year"


def test_cli_reads_case_file_and_prints_report(capsys, write_case, homestead_case):
    assert savings.main([str(write_case(homestead_case))]) == 0
    out = capsys.readouterr().out
    assert "Estimated savings so far: $1,060 to $1,490 per year" in out
    assert "not predictions" in out


def test_cli_json_output(capsys, write_case, homestead_case):
    assert savings.main([str(write_case(homestead_case)), "--json", "--low-fraction", "0.25"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["low_fraction"] == 0.25
    assert data["protest"]["high"] == pytest.approx(860.0)


def test_cli_reports_errors_with_exit_code_2(capsys):
    assert savings.main(["--appraised", "100", "--argued", "90"]) == 2
    assert "tax_rates.total is required" in capsys.readouterr().err
    assert savings.main(["--appraised", "100", "--argued", "90", "--total-rate", "2",
                         "--low-fraction", "0.9", "--high-fraction", "0.1"]) == 2


# --- capped homesteads: market value above the taxable appraised value -------------------

def test_argued_value_between_appraised_and_market_saves_nothing(capped_case):
    estimate = savings.estimate_savings(capped_case)               # appraised 462,000; argued 470,000
    assert estimate.protest == savings.SavingsRange(0, 0)
    assert estimate.reduction == 0 and estimate.protest_blocked
    assert estimate.total.low == estimate.total.high == pytest.approx(660.0)      # the 65+ exemption only


def test_blocked_meter_explains_in_plain_words(capped_case):
    meter = savings.meter_for(savings.estimate_savings(capped_case))
    assert meter.startswith("Estimated savings so far: $660 per year. ")
    assert "No protest savings this year: your argued value is above the capped appraised value" in meter
    assert "A lower market value still limits how fast the cap closes the gap." in meter
    assert "-" not in meter.split(". ")[0]                         # never a negative number
    assert savings.meter_line(savings.estimate_savings(capped_case)) == "Estimated savings so far: $660 per year"


def test_argued_value_below_the_capped_value_saves_only_the_difference(capped_case):
    capped_case["argued_value"] = 440000                           # market 520,000, appraised 462,000
    estimate = savings.estimate_savings(capped_case)
    assert not estimate.protest_blocked
    assert estimate.reduction == 22000                             # not the 80,000 market-value reduction
    # low scenario: half of the 80,000 market reduction only reaches 480,000, which is still above the 462,000 cap
    assert estimate.protest.low == 0
    assert estimate.protest.high == pytest.approx(484.0)           # all of it: 22,000 at 2.2 per $100
    assert savings.meter_for(estimate) == "Estimated savings so far: $660 to $1,144 per year"


def test_argued_value_equal_to_the_capped_value_is_blocked(capped_case):
    capped_case["argued_value"] = 462000
    estimate = savings.estimate_savings(capped_case)
    assert estimate.protest_blocked and estimate.protest.high == 0


def test_exemptions_are_priced_on_the_lower_of_argued_and_appraised_value():
    case = {"subject": {"appraised_value": 100000, "market_value": 200000}, "argued_value": 150000,
            "tax_rates": {"total": 2.0, "school": 1.0},
            "exemptions": {"eligible": [{"name": "Big", "amount": 250000, "applies_to": "all"}]}}
    [priced] = savings.estimate_savings(case).exemptions
    assert priced.annual == pytest.approx(2000.0)                  # capped at the 100,000 taxable value


def test_without_market_value_the_protest_always_has_savings(homestead_case):
    estimate = savings.estimate_savings(homestead_case)
    assert not estimate.protest_blocked
    assert savings.meter_for(estimate) == savings.meter_line(estimate)


def test_cli_prints_the_blocked_message(capsys, write_case, capped_case):
    assert savings.main([str(write_case(capped_case))]) == 0
    out = capsys.readouterr().out
    assert "Protest: $0 per year. No protest savings this year:" in out
    assert "Estimated savings so far: $660 per year." in out
