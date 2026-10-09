#!/usr/bin/env python3
"""Estimate annual property-tax savings from a protest and from exemptions.

Tax rates are dollars per $100 of taxable value and always come from the caller
(case.json ``tax_rates``). Nothing here knows any exemption amount or rate.

The low and high figures are *settlement scenarios*, not predictions: they take
``low_fraction`` and ``high_fraction`` of the market-value reduction argued in the
protest (defaults 0.5 and 1.0). The tax only falls to the extent the reduced market
value drops below the taxable appraised value, so a capped homestead can save less
than the market-value reduction suggests, or nothing. Exemptions count at full value
in both scenarios, since they depend on qualifying, not on negotiation.

With ``tax_rates.school_ceiling`` true a school tax ceiling holds school tax fixed, so
no school-tax savings are counted: the protest and "all" exemptions use (total - school)
and school exemptions save $0.

Usage:
  python savings.py case.json [--meter]
  python savings.py --appraised 400000 --argued 360000 --total-rate 2.1 --meter
  python savings.py --market 500000 --appraised 400000 --argued 450000 --total-rate 2.1
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from fmt import money, read_json, use_utf8_output

DEFAULT_LOW_FRACTION = 0.5
DEFAULT_HIGH_FRACTION = 1.0
MAX_RATE = 100   # dollars of tax per $100 of value; a higher "rate" is not a rate

NO_PROTEST_SAVINGS = (
    "No protest savings this year: your argued value is above the capped appraised value your tax bill "
    "is based on. A lower market value still limits how fast the cap closes the gap."
)
SCHOOL_CEILING_NOTE = (
    "A school tax ceiling applies, so school-tax savings are not counted; "
    "the real figure depends on the ceiling amount."
)


@dataclass(frozen=True)
class SavingsRange:
    low: float
    high: float

    def __add__(self, other: "SavingsRange") -> "SavingsRange":
        return SavingsRange(round(self.low + other.low, 2), round(self.high + other.high, 2))


@dataclass(frozen=True)
class ExemptionSavings:
    name: str
    amount: Optional[float]      # None for a total exemption or one that is not quantified
    applies_to: Optional[str]    # "school", "all", or None
    annual: float                # estimated annual tax saved
    quantified: bool


@dataclass(frozen=True)
class SavingsEstimate:
    reduction: float                # reduction below the taxable appraised value (what can lower the tax)
    protest: SavingsRange
    exemptions: List[ExemptionSavings]
    total: SavingsRange
    low_fraction: float
    high_fraction: float
    protest_blocked: bool = False   # argued value is not below the taxable appraised value
    school_ceiling: bool = False    # school-tax savings are not counted


def check_fractions(low_fraction: float, high_fraction: float) -> None:
    if not 0 <= low_fraction <= high_fraction <= 1:
        raise ValueError(
            f"fractions must satisfy 0 <= low <= high <= 1 (got low={low_fraction}, high={high_fraction})"
        )


def tax_on(value: float, rate_per_100: float) -> float:
    return value / 100 * rate_per_100


def _require_number(value: Any, label: str, minimum: float = 0.0, maximum: Optional[float] = None) -> float:
    """A finite number within bounds, so savings can never exceed the tax bill."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number (got {value!r})")
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"between {minimum:g} and {maximum:g}" if maximum is not None else f"at least {minimum:g}"
        raise ValueError(f"{label} must be {bound} (got {value})")
    return float(value)


def protest_savings(appraised_value: float, argued_value: float, total_rate: float,
                    low_fraction: float = DEFAULT_LOW_FRACTION,
                    high_fraction: float = DEFAULT_HIGH_FRACTION,
                    market_value: Optional[float] = None) -> SavingsRange:
    """Annual tax saved in the low and high settlement scenarios.

    The scenario fraction is applied to the market-value reduction first; the result is then
    capped at the taxable appraised value: taxable = min(appraised, market - f x (market - argued)).
    Without a market value (no cap) this is simply f x (appraised - argued) x rate / 100.
    """
    check_fractions(low_fraction, high_fraction)
    appraised = _require_number(appraised_value, "appraised value", 0.0)
    argued = _require_number(argued_value, "argued value", 0.0)
    market = appraised if market_value is None else _require_number(market_value, "market value", appraised)
    rate = _require_number(total_rate, "tax rate", 0.0, MAX_RATE)
    reduction = max(market - argued, 0)

    def saved(fraction: float) -> float:
        taxable = min(appraised, market - fraction * reduction)
        return round(tax_on(max(appraised - taxable, 0), rate), 2)

    return SavingsRange(saved(low_fraction), saved(high_fraction))


def effective_rates(tax_rates: Mapping[str, Any]) -> Dict[str, float]:
    """Rates that count toward savings: 'school', 'all' (exemptions) and 'protest'."""
    total = _require_number(tax_rates.get("total"), "tax_rates.total", 0.0, MAX_RATE)
    school = tax_rates.get("school")
    if school is not None:
        school = _require_number(school, "tax_rates.school", 0.0, MAX_RATE)
        if school > total:
            raise ValueError(f"tax_rates.school ({school:g}) must not exceed tax_rates.total ({total:g})")
    if tax_rates.get("school_ceiling"):
        if school is None:
            raise ValueError("tax_rates.school is required when tax_rates.school_ceiling is true")
        return {"school": 0.0, "all": total - school, "protest": total - school}
    rates = {"all": total, "protest": total}
    if school is not None:
        rates["school"] = school
    return rates


def exemption_savings(exemptions: Sequence[Mapping[str, Any]], tax_rates: Mapping[str, Any],
                      taxable_value: float) -> List[ExemptionSavings]:
    """Price each exemption. An exemption cannot remove more than the taxable value."""
    rates = effective_rates(tax_rates)
    return [_price_exemption(item, rates, taxable_value) for item in exemptions]


def _price_exemption(item: Mapping[str, Any], rates: Mapping[str, float],
                     taxable_value: float) -> ExemptionSavings:
    name = item["name"]
    if item.get("kind") == "total":
        return ExemptionSavings(name, None, "all", round(tax_on(taxable_value, rates["all"]), 2), True)
    amount, applies_to = item.get("amount"), item.get("applies_to")
    if not amount or not applies_to:
        return ExemptionSavings(name, amount, applies_to, 0.0, False)
    _require_number(amount, f"exemption '{name}' amount", 0.0)
    key = "school" if applies_to == "school" else "all"
    if key not in rates:
        raise ValueError(f"tax_rates.school is required to price an exemption that applies to '{applies_to}'")
    saved = tax_on(min(amount, taxable_value), rates[key])
    return ExemptionSavings(name, amount, applies_to, round(saved, 2), True)


def estimate_savings(case: Mapping[str, Any], low_fraction: Optional[float] = None,
                     high_fraction: Optional[float] = None) -> SavingsEstimate:
    """Savings for a (possibly still partial) case dict.

    Reads subject.appraised_value (the taxable value on the notice, capped for some homesteads),
    subject.market_value (defaults to the appraised value), argued_value, tax_rates,
    exemptions.eligible and settlement_scenarios. A missing argued_value means no protest savings
    yet. Inputs are validated so the estimate can never exceed the tax bill.
    """
    scenarios = case.get("settlement_scenarios") or {}
    low = _first(low_fraction, scenarios.get("low_fraction"), DEFAULT_LOW_FRACTION)
    high = _first(high_fraction, scenarios.get("high_fraction"), DEFAULT_HIGH_FRACTION)
    check_fractions(low, high)
    tax_rates = case.get("tax_rates") or {}
    if "total" not in tax_rates:
        raise ValueError("tax_rates.total is required (dollars of tax per $100 of value)")
    rates = effective_rates(tax_rates)
    subject = case.get("subject") or {}
    appraised, argued = subject.get("appraised_value"), case.get("argued_value")
    if argued is not None and appraised is None:
        raise ValueError("subject.appraised_value is required when argued_value is given")
    if appraised is not None:
        _require_number(appraised, "subject.appraised_value", 0.0)
    market = subject.get("market_value", appraised)
    protest, reduction, blocked = SavingsRange(0.0, 0.0), 0.0, False
    if argued is not None:
        _require_number(argued, "argued_value", 0.0)
        market = _require_number(market, "subject.market_value", appraised)
        if argued >= market:
            raise ValueError(f"argued_value ({argued:,.0f}) must be below the market value ({market:,.0f})")
        protest = protest_savings(appraised, argued, rates["protest"], low, high, market)
        reduction = max(appraised - argued, 0)
        blocked = argued >= appraised
    taxable = min(argued, appraised) if argued is not None else (appraised or 0)
    eligible = (case.get("exemptions") or {}).get("eligible", [])
    priced = exemption_savings(eligible, tax_rates, taxable)
    # Overlapping exemptions (say a school exemption and a total one) cannot save more than the whole bill.
    exempt_total = min(round(sum(item.annual for item in priced), 2), round(tax_on(taxable, rates["all"]), 2))
    total = protest + SavingsRange(exempt_total, exempt_total)
    return SavingsEstimate(reduction, protest, priced, total, low, high, blocked,
                           bool(tax_rates.get("school_ceiling")))


def _first(*values: Optional[float]) -> float:
    return next(value for value in values if value is not None)


def range_text(low: float, high: float) -> str:
    """'$430 to $860', or a single figure when both round to the same amount."""
    low_text, high_text = money(low), money(high)
    return low_text if low_text == high_text else f"{low_text} to {high_text}"


def format_meter(low: float, high: float) -> str:
    """The one-line savings meter shown to the user."""
    return f"Estimated savings so far: {range_text(low, high)} per year"


def meter_line(estimate: SavingsEstimate) -> str:
    return format_meter(estimate.total.low, estimate.total.high)


def savings_notes(estimate: SavingsEstimate) -> List[str]:
    """Plain-language caveats that must accompany the savings figures."""
    notes = []
    if estimate.protest_blocked:
        notes.append(NO_PROTEST_SAVINGS)
    if estimate.school_ceiling:
        notes.append(SCHOOL_CEILING_NOTE)
    return notes


def meter_for(estimate: SavingsEstimate) -> str:
    """The meter, followed by plain explanations when the protest cannot lower the tax or a ceiling applies."""
    notes = savings_notes(estimate)
    return f"{meter_line(estimate)}. {' '.join(notes)}" if notes else meter_line(estimate)


def scenario_text(estimate: SavingsEstimate) -> str:
    """'50% and 100% of the argued reduction' (the low and high settlement scenarios)."""
    return (f"{estimate.low_fraction * 100:g}% and {estimate.high_fraction * 100:g}% "
            "of the argued reduction")


# --- command line -----------------------------------------------------------

def _format_report(estimate: SavingsEstimate) -> str:
    if estimate.protest_blocked:
        lines = [f"Protest: $0 per year. {NO_PROTEST_SAVINGS}"]
    else:
        lines = [f"Protest ({scenario_text(estimate)}, a {money(estimate.reduction)} reduction): "
                 f"{money(estimate.protest.low)} to {money(estimate.protest.high)} per year"]
    for item in estimate.exemptions:
        label = money(item.annual) if item.quantified else "not quantified"
        lines.append(f"Exemption - {item.name}: {label}")
    lines.append(meter_for(estimate))
    lines.append("Scenarios are settlement assumptions, not predictions.")
    return "\n".join(lines)


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate protest and exemption savings.")
    parser.add_argument("case", nargs="?", type=Path, help="case.json (may be partial)")
    parser.add_argument("--appraised", type=float, help="taxable appraised value on the notice (overrides the case)")
    parser.add_argument("--market", type=float, help="CAD market value on the notice (default: the appraised value)")
    parser.add_argument("--argued", type=float, help="argued value (overrides the case)")
    parser.add_argument("--total-rate", type=float, help="total tax rate per $100 (overrides the case)")
    parser.add_argument("--school-rate", type=float, help="school tax rate per $100 (overrides the case)")
    parser.add_argument("--school-ceiling", action="store_true",
                        help="a school tax ceiling applies: do not count school-tax savings")
    parser.add_argument("--low-fraction", type=float, help=f"default {DEFAULT_LOW_FRACTION}")
    parser.add_argument("--high-fraction", type=float, help=f"default {DEFAULT_HIGH_FRACTION}")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--meter", action="store_true", help="print only the savings-meter line")
    mode.add_argument("--json", action="store_true", help="print the full estimate as JSON")
    return parser.parse_args(argv)


def _case_from_args(args: argparse.Namespace) -> Dict[str, Any]:
    case: Dict[str, Any] = read_json(args.case) if args.case else {}
    if not isinstance(case, dict):
        raise ValueError(f"{args.case}: expected a JSON object")
    subject = case.setdefault("subject", {})
    if args.appraised is not None:
        subject["appraised_value"] = args.appraised
    if args.market is not None:
        subject["market_value"] = args.market
    if args.argued is not None:
        case["argued_value"] = args.argued
    rates = case.setdefault("tax_rates", {})
    if args.total_rate is not None:
        rates["total"] = args.total_rate
    if args.school_rate is not None:
        rates["school"] = args.school_rate
    if args.school_ceiling:
        rates["school_ceiling"] = True
    return case


def main(argv: Optional[Sequence[str]] = None) -> int:
    use_utf8_output()
    args = _parse_args(argv)
    try:
        estimate = estimate_savings(_case_from_args(args), args.low_fraction, args.high_fraction)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(asdict(estimate), indent=2))
    elif args.meter:
        print(meter_for(estimate))
    else:
        print(_format_report(estimate))
    return 0


if __name__ == "__main__":
    sys.exit(main())
