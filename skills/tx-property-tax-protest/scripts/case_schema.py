"""Load and validate case.json with clear, field-level error messages.

The schema is declared as data (see ``CASE_FIELDS``). Every problem found is
reported in one pass, e.g. ``comps[2].price: required field is missing``.
The human-readable contract lives in references/case-schema.md.
"""
from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from fmt import read_json, strict_date
from savings import DEFAULT_HIGH_FRACTION, DEFAULT_LOW_FRACTION, MAX_RATE

Check = Callable[[Any, str, List[str]], None]

PATHS = ("homestead", "rental")
STRATEGIES = ("market_value", "unequal_appraisal", "both")
PRICE_TYPES = ("sale", "listing", "estimate")
APPLIES_TO = ("school", "all")
EXEMPTION_KINDS = ("fixed", "total")
MAX_NUMBER = 1_000_000_000_000        # sanity limit for every number (a trillion dollars or square feet)
MAX_YEAR = 9999
CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")   # everything except tab and newline


class CaseError(ValueError):
    """Raised when case.json is unreadable or fails validation."""

    def __init__(self, errors: List[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class Field:
    check: Check
    required: bool = False


def req(check: Check) -> Field:
    return Field(check, True)


def opt(check: Check) -> Field:
    return Field(check, False)


# --- primitive checks -------------------------------------------------------

def _describe(value: Any) -> str:
    return repr(value) if not isinstance(value, (dict, list)) else type(value).__name__


def text() -> Check:
    def check(value: Any, path: str, errors: List[str]) -> None:
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{path}: must be a non-empty string (got {_describe(value)})")
            return
        bad = CONTROL_CHARACTERS.search(value)
        if bad:
            errors.append(f"{path}: contains a control character (code {ord(bad.group()):#04x}); "
                          "remove it (only tab and line breaks are allowed)")
    return check


def _in_range(value: Any, path: str, errors: List[str]) -> bool:
    """True for a real number of sane size; otherwise records why not."""
    if isinstance(value, float) and not math.isfinite(value):
        errors.append(f"{path}: must be a finite number (got {value})")
    elif abs(value) > MAX_NUMBER:
        errors.append(f"{path}: is too large (limit {MAX_NUMBER:,})")
    else:
        return True
    return False


def number(minimum: Optional[float] = None, maximum: Optional[float] = None,
           positive: bool = False) -> Check:
    def check(value: Any, path: str, errors: List[str]) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{path}: must be a number (got {_describe(value)})")
        elif not _in_range(value, path, errors):
            return
        elif positive and value <= 0:
            errors.append(f"{path}: must be greater than 0 (got {value})")
        elif minimum is not None and value < minimum:
            errors.append(f"{path}: must be at least {minimum:g} (got {value})")
        elif maximum is not None and value > maximum:
            errors.append(f"{path}: must be at most {maximum:g} (got {value})")
    return check


def year() -> Check:
    def check(value: Any, path: str, errors: List[str]) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append(f"{path}: must be a whole number (got {_describe(value)})")
        elif not 1 <= value <= MAX_YEAR:
            errors.append(f"{path}: must be a year between 1 and {MAX_YEAR} (got {value})")
    return check


def iso_date() -> Check:
    def check(value: Any, path: str, errors: List[str]) -> None:
        try:
            strict_date(value)
        except ValueError:
            errors.append(f"{path}: must be a date written YYYY-MM-DD (got {_describe(value)})")
    return check


def boolean() -> Check:
    def check(value: Any, path: str, errors: List[str]) -> None:
        if not isinstance(value, bool):
            errors.append(f"{path}: must be true or false (got {_describe(value)})")
    return check


def choice(options: tuple) -> Check:
    def check(value: Any, path: str, errors: List[str]) -> None:
        if value not in options:
            errors.append(f"{path}: must be one of {', '.join(options)} (got {_describe(value)})")
    return check


def text_list() -> Check:
    return array(text())


def array(item: Check, min_items: int = 0) -> Check:
    def check(value: Any, path: str, errors: List[str]) -> None:
        if not isinstance(value, list):
            errors.append(f"{path}: must be a list (got {_describe(value)})")
            return
        if len(value) < min_items:
            errors.append(f"{path}: needs at least {min_items} item(s) (got {len(value)})")
        for index, element in enumerate(value):
            item(element, f"{path}[{index}]", errors)
    return check


def obj(fields: Dict[str, Field]) -> Check:
    def check(value: Any, path: str, errors: List[str]) -> None:
        if not isinstance(value, dict):
            errors.append(f"{path}: must be an object (got {_describe(value)})")
            return
        for key in value:
            if key not in fields and not key.startswith("_"):
                errors.append(_unknown_field(path, key, fields))
        for name, field in fields.items():
            child = f"{path}.{name}" if path else name
            if name not in value or value[name] is None:
                if field.required:
                    errors.append(f"{child}: required field is missing")
                continue
            field.check(value[name], child, errors)
    return check


def _unknown_field(path: str, key: str, fields: Dict[str, Field]) -> str:
    where = f"{path}.{key}" if path else key
    close = difflib.get_close_matches(key, list(fields), n=1)
    hint = f" (did you mean '{close[0]}'?)" if close else ""
    return f"{where}: unknown field{hint}; prefix with '_' to keep a free-form note"


# --- schema -----------------------------------------------------------------

EXEMPTION_FIELDS: Dict[str, Field] = {
    "name": req(text()),
    "amount": opt(number(minimum=0)),
    "applies_to": opt(choice(APPLIES_TO)),
    "kind": opt(choice(EXEMPTION_KINDS)),
    "cite": opt(text()),
    "how_to_claim": opt(text()),
    "documents": opt(text_list()),
    "note": opt(text()),
}

CASE_FIELDS: Dict[str, Field] = {
    "path": req(choice(PATHS)),
    "tax_year": req(year()),
    "county": req(text()),
    "prepared_on": opt(iso_date()),
    "cad": req(obj({
        "name": req(text()),
        "address": req(text()),
        "phone": opt(text()),
        "website": opt(text()),
        "protest_addressee": opt(text()),
    })),
    "filing": req(obj({
        "methods": req(array(obj({"method": req(text()), "detail": opt(text())}), min_items=1)),
        "hearing_documents": opt(text_list()),
        "notes": opt(text_list()),
    })),
    "notice_date": opt(iso_date()),
    "hearing_date": opt(iso_date()),
    "arb_order_date": opt(iso_date()),
    "deadlines": opt(array(obj({
        "event": req(text()),
        "date": req(iso_date()),
        "statute": opt(text()),
        "note": opt(text()),
    }))),
    "owner": req(obj({
        "name": req(text()),
        "mailing_address": req(text()),
        "phone": opt(text()),
        "email": opt(text()),
    })),
    "subject": req(obj({
        "address": req(text()),
        "cad_account": req(text()),
        "legal_description": opt(text()),
        "subdivision": opt(text()),
        "sqft": req(number(positive=True)),
        "year_built": opt(year()),
        "beds": opt(number(minimum=0)),
        "baths": opt(number(minimum=0)),
        "lot_sqft": opt(number(positive=True)),
        "appraised_value": req(number(positive=True)),
        "market_value": opt(number(positive=True)),
        "land_value": opt(number(minimum=0)),
        "improvement_value": opt(number(minimum=0)),
        "value_history": opt(array(obj({
            "year": req(year()),
            "value": req(number(minimum=0)),
        }))),
        "purchase_price": opt(number(positive=True)),
        "purchase_date": opt(iso_date()),
    })),
    "legal_basis": req(obj({
        "market_value_cite": opt(text()),
        "unequal_cite": opt(text()),
        "protest_form": opt(text()),
        "valuation_date": opt(iso_date()),
        "additional": opt(array(obj({"label": req(text()), "cite": req(text())}))),
    })),
    "tax_rates": req(obj({
        "total": req(number(positive=True, maximum=MAX_RATE)),
        "school": opt(number(positive=True, maximum=MAX_RATE)),
        "school_ceiling": opt(boolean()),
        "source": opt(text()),
    })),
    "exemptions": opt(obj({
        "on_file": opt(array(obj(EXEMPTION_FIELDS))),
        "eligible": opt(array(obj(EXEMPTION_FIELDS))),
    })),
    "comps": opt(array(obj({
        "address": req(text()),
        "price": req(number(positive=True)),
        "price_type": opt(choice(PRICE_TYPES)),
        "sale_date": opt(iso_date()),
        "sqft": opt(number(positive=True)),
        "year_built": opt(year()),
        "beds": opt(number(minimum=0)),
        "baths": opt(number(minimum=0)),
        "lot_sqft": opt(number(positive=True)),
        "distance_mi": opt(number(minimum=0)),
        "source": opt(text()),
        "adjustments": opt(array(obj({"label": req(text()), "amount": req(number())}))),
        "notes": opt(text()),
    }))),
    "neighbors": opt(array(obj({
        "address": req(text()),
        "appraised_value": req(number(positive=True)),
        "sqft": opt(number(positive=True)),
        "year_built": opt(year()),
        "cad_account": opt(text()),
    }))),
    "market_notes": opt(text_list()),
    "arguments": opt(text_list()),
    "strategy": opt(choice(STRATEGIES)),
    "argued_value": req(number(positive=True)),
    "settlement_scenarios": opt(obj({
        "low_fraction": opt(number(minimum=0, maximum=1)),
        "high_fraction": opt(number(minimum=0, maximum=1)),
    })),
    "income": opt(obj({
        "gross_rent": req(number(positive=True)),
        "vacancy_pct": req(number(minimum=0, maximum=100)),
        "expenses": req(array(obj({"label": req(text()), "amount": req(number(minimum=0))}))),
        "cap_rate_pct": req(number(positive=True)),
        "cap_rate_source": req(text()),
        "rent_source": opt(text()),
        "circuit_breaker_note": opt(text()),
    })),
    "disclaimer_text": opt(text()),
}


# --- cross-field rules ------------------------------------------------------

def _strategy(case: Dict[str, Any]) -> str:
    return case.get("strategy") or "market_value"


def _sale_comps(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Only sales count as comparable-sale evidence; listings and estimates are supporting data."""
    return [c for c in case.get("comps", []) if c.get("price_type", "sale") == "sale"]


def _usable_neighbors(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [n for n in case.get("neighbors", []) if n.get("sqft")]


def _cross_checks(case: Dict[str, Any]) -> List[str]:
    """Rules that span several fields. Runs only on structurally valid data."""
    errors: List[str] = []
    for check in (_check_path_blocks, _check_strategy_inputs, _check_exemptions, _check_pricing, _check_rates,
                  _check_dates, _check_scenarios, _check_comp_values, _check_income):
        check(case, errors)
    return errors


def _check_path_blocks(case: Dict[str, Any], errors: List[str]) -> None:
    if case["path"] == "homestead" and "income" in case:
        errors.append("income: only allowed when path is 'rental'")
    if case["path"] == "rental":
        sales = _strategy(case) in ("market_value", "both") and _sale_comps(case)
        if not (sales or _usable_neighbors(case) or "income" in case):
            errors.append("rental cases need at least one of: sale comps (strategy market_value or both), "
                          "neighbors with sqft (unequal appraisal), or an income block")


def _check_strategy_inputs(case: Dict[str, Any], errors: List[str]) -> None:
    strategy = _strategy(case)
    basis = case["legal_basis"]
    if strategy in ("market_value", "both"):
        if not basis.get("market_value_cite"):
            errors.append(f"legal_basis.market_value_cite: required when strategy is '{strategy}'")
        income_leads = case["path"] == "rental" and "income" in case
        if not _sale_comps(case) and not income_leads:
            extra = " (listings and estimates are not used in the median)" if case.get("comps") else ""
            errors.append(f"comps: at least one comparable with price_type 'sale' is required "
                          f"when strategy is '{strategy}'{extra}")
    if strategy in ("unequal_appraisal", "both"):
        if not basis.get("unequal_cite"):
            errors.append(f"legal_basis.unequal_cite: required when strategy is '{strategy}'")
        if not _usable_neighbors(case):
            errors.append(f"neighbors: at least one neighbor with sqft is required when strategy is '{strategy}'")


def _check_exemptions(case: Dict[str, Any], errors: List[str]) -> None:
    exemptions = case.get("exemptions") or {}
    for group in ("on_file", "eligible"):
        for index, item in enumerate(exemptions.get(group, [])):
            where = f"exemptions.{group}[{index}]"
            _check_exemption_item(item, where, group == "eligible", case, errors)


def _check_exemption_item(item: Dict[str, Any], where: str, is_eligible: bool,
                          case: Dict[str, Any], errors: List[str]) -> None:
    if is_eligible and not item.get("how_to_claim"):
        errors.append(f"{where}.how_to_claim: required for eligible exemptions (used in the checklist)")
    is_total = item.get("kind") == "total"
    has_amount = bool(item.get("amount"))
    if has_amount and not is_total and not item.get("applies_to"):
        errors.append(f"{where}.applies_to: required when amount is given (school or all)")
    school_priced = has_amount and not is_total and item.get("applies_to") == "school"
    if is_eligible and school_priced and "school" not in case["tax_rates"]:
        errors.append(f"tax_rates.school: required because {where} applies to school taxes")


def _check_pricing(case: Dict[str, Any], errors: List[str]) -> None:
    """market_value defaults to appraised_value; the protest must ask for less than the market value."""
    subject = case["subject"]
    appraised = subject["appraised_value"]
    market = subject.get("market_value", appraised)
    if market < appraised:
        errors.append(
            f"subject.market_value: must be at least subject.appraised_value ({appraised:,.0f}); "
            "the taxable appraised value cannot exceed the market value"
        )
    if case["argued_value"] >= market:
        field = "subject.market_value" if "market_value" in subject else "subject.appraised_value"
        errors.append(f"argued_value: must be below {field} ({market:,.0f}); a protest asks for a reduction")


def _check_rates(case: Dict[str, Any], errors: List[str]) -> None:
    rates = case["tax_rates"]
    if "school" in rates and rates["school"] > rates["total"]:
        errors.append(f"tax_rates.school: must not exceed tax_rates.total ({rates['total']:g}); "
                      "the school rate is part of the total rate")
    if rates.get("school_ceiling") and "school" not in rates:
        errors.append("tax_rates.school: required when tax_rates.school_ceiling is true")


def _check_dates(case: Dict[str, Any], errors: List[str]) -> None:
    if "notice_date" not in case and not case.get("deadlines"):
        errors.append("notice_date: provide notice_date (deadlines are computed from it) or a deadlines list")
    notice, prepared = case.get("notice_date"), case.get("prepared_on")
    if notice and int(notice[:4]) != case["tax_year"]:
        errors.append(f"notice_date: year {notice[:4]} must equal tax_year {case['tax_year']}")
    if notice and prepared and prepared < notice:
        errors.append(f"prepared_on: {prepared} is earlier than notice_date {notice}")


def _check_scenarios(case: Dict[str, Any], errors: List[str]) -> None:
    """Order check on the fractions as they will be used, after the defaults fill in what is missing."""
    scenarios = case.get("settlement_scenarios") or {}
    low = scenarios.get("low_fraction", DEFAULT_LOW_FRACTION)
    high = scenarios.get("high_fraction", DEFAULT_HIGH_FRACTION)
    if low > high:
        low_note = "" if "low_fraction" in scenarios else ", the default"
        high_note = "" if "high_fraction" in scenarios else ", the default"
        changed = "low_fraction" if "low_fraction" in scenarios else "high_fraction"
        errors.append(f"settlement_scenarios: low_fraction ({low:g}{low_note}) must not exceed "
                      f"high_fraction ({high:g}{high_note}); change {changed} or set both")


def _check_comp_values(case: Dict[str, Any], errors: List[str]) -> None:
    for index, comp in enumerate(case.get("comps", [])):
        adjusted = comp["price"] + sum(a["amount"] for a in comp.get("adjustments", []))
        if adjusted <= 0:
            errors.append(f"comps[{index}]: price plus adjustments must be above 0 (got {adjusted:,.0f}); "
                          f"check comps[{index}].adjustments")


def _check_income(case: Dict[str, Any], errors: List[str]) -> None:
    income = case.get("income")
    if not income:
        return
    effective = income["gross_rent"] * (1 - income["vacancy_pct"] / 100)
    noi = effective - sum(e["amount"] for e in income["expenses"])
    if noi <= 0:
        errors.append(
            f"income: net operating income must be above 0 (gross_rent less vacancy_pct and expenses gives "
            f"{noi:,.0f}); check income.gross_rent, income.vacancy_pct and income.expenses"
        )


# --- warnings: odd but not invalid -------------------------------------------

def case_warnings(case: Dict[str, Any]) -> List[str]:
    """Things worth a second look. They never block a build; only the case's own dates are used."""
    notice = _date_or_none(case.get("notice_date"))
    warnings = []
    for name in ("hearing_date", "arb_order_date"):
        given = _date_or_none(case.get(name))
        if notice and given and given < notice:
            warnings.append(f"{name} {given} is earlier than notice_date {notice}")
    warnings += _sale_date_warnings(case)
    return warnings


def _date_or_none(value: Optional[str]):
    return strict_date(value) if value else None


def _sale_date_warnings(case: Dict[str, Any]) -> List[str]:
    own_dates = [d for d in (_date_or_none(case.get(k)) for k in
                             ("prepared_on", "notice_date", "hearing_date", "arb_order_date")) if d]
    prepared = _date_or_none(case.get("prepared_on"))
    latest = prepared or (max(own_dates) if own_dates else None)
    valuation = _date_or_none((case.get("legal_basis") or {}).get("valuation_date")) or \
        strict_date(f"{case['tax_year']:04d}-01-01")
    try:
        oldest = valuation.replace(year=valuation.year - 5)
    except ValueError:                      # Feb 29
        oldest = valuation.replace(year=valuation.year - 5, day=28)
    warnings = []
    for index, comp in enumerate(case.get("comps", [])):
        sold = _date_or_none(comp.get("sale_date"))
        if not sold:
            continue
        where = f"comps[{index}].sale_date {sold}"
        if latest and sold > latest:
            warnings.append(f"{where} is later than {'prepared_on' if prepared else 'the latest date in the case'} "
                            f"({latest})")
        if sold < oldest:
            warnings.append(f"{where} is more than 5 years before the valuation date {valuation}")
    return warnings


# --- public API -------------------------------------------------------------

def validate_case(data: Any) -> List[str]:
    """Return every validation problem found (empty list means valid)."""
    errors: List[str] = []
    obj(CASE_FIELDS)(data, "", errors)
    if errors:
        return errors
    return _cross_checks(data)


def drop_nulls(value: Any) -> Any:
    """Treat JSON null as 'not provided' everywhere, so callers can rely on .get()."""
    if isinstance(value, dict):
        return {k: drop_nulls(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [drop_nulls(v) for v in value]
    return value


def load_case(path: Path) -> Dict[str, Any]:
    """Read case.json and validate it; raise CaseError with all problems."""
    try:
        data = read_json(path)
    except ValueError as exc:
        raise CaseError([str(exc)])
    errors = validate_case(data)
    if errors:
        raise CaseError(errors)
    return drop_nulls(data)
